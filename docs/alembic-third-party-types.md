# Alembic + Third-Party Column Types (pgvector, etc.)

## The Problem

When you run `alembic revision --autogenerate`, Alembic generates migration files
by calling `repr()` on each column type and pasting it into the file.

**Built-in types** work fine because Alembic auto-imports them:
```python
# Alembic auto-generates these imports
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# So this works:
sa.Column('name', sa.String(length=255))
sa.Column('metadata', postgresql.JSONB())
```

**Third-party types** break because Alembic does NOT auto-import them:
```python
# pgvector's Vector.__repr__() returns the fully-qualified path
# but Alembic never adds the import:
sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768))
#                       ^^^^^^^^ NameError — not imported!
```

This is a known Alembic limitation. It has no plugin system to discover
third-party type imports. Same issue affects `geoalchemy2`, `sqlalchemy-utils`, etc.

## The Fix: `render_item` Hook

Alembic provides a `render_item` callback that intercepts type rendering during
autogenerate. We use it in `alembic/env.py`:

```python
from pgvector.sqlalchemy import Vector

def render_item(type_, obj, autogen_context):
    """Teach Alembic how to render pgvector's Vector type."""
    if type_ == "type" and isinstance(obj, Vector):
        # This adds the import to the generated migration file
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        # This is what gets written in the migration instead of repr()
        return f"Vector(dim={obj.dim})"
    return False  # default rendering for everything else
```

Then pass it to **both** `context.configure()` calls (offline and online):
```python
context.configure(
    ...,
    render_item=render_item,
)
```

### Result

**Before** (broken — no import):
```python
sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True)
```

**After** (correct — import added automatically):
```python
from pgvector.sqlalchemy import Vector
# ...
sa.Column('embedding', Vector(dim=768), nullable=True)
```

## Adding More Third-Party Types

If you add another third-party column type in the future (e.g., `geoalchemy2`),
extend the same `render_item` function:

```python
def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector(dim={obj.dim})"
    # Add more third-party types here:
    # if type_ == "type" and isinstance(obj, Geometry):
    #     autogen_context.imports.add("from geoalchemy2 import Geometry")
    #     return f"Geometry(geometry_type='{obj.geometry_type}', srid={obj.srid})"
    return False
```

## PostgreSQL Extension Must Be Enabled First

Even after fixing the Python import, the migration will fail with:
```
asyncpg.exceptions.UndefinedObjectError: type "vector" does not exist
```

This means PostgreSQL itself doesn't know what `VECTOR` is. The pgvector
**extension** must be enabled before any table can use the `vector` column type.

### How we handle it

We use a **separate, dedicated migration** that runs before any table migration
that uses `vector`:

```
alembic/versions/
  f3327c5011d1_create_bots_table.py          # 1st
  a0000000001_enable_pg_extensions.py         # 2nd — CREATE EXTENSION vector
  <hash>_create_document_related_tables.py    # 3rd — uses Vector(768) columns
```

The extension migration (`a0000000001_enable_pg_extensions.py`):
```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
```

### Why a separate migration?

- Extensions are a **database-level prerequisite**, not a table-level concern
- If you ever add more extensions (`pg_trgm`, `uuid-ossp`, etc.), they go here
- Keeps table migrations clean — they don't need to worry about extensions
- Easy to see at a glance what extensions the project requires

### Docker / fresh database note

If your PostgreSQL runs in Docker, `pgvector` must be **installed in the
Docker image**. The standard `postgres` image does NOT include it.
Use `pgvector/pgvector:pg16` (or your PG version) instead:

```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16   # NOT postgres:16
```

`CREATE EXTENSION vector` only works if the extension files are installed
in the PostgreSQL server. The migration enables it; the Docker image provides it.

## Duplicate Index Gotcha

Watch out for defining indexes in **two places**:

```python
# This creates an auto-named index (ix_documents_status):
status = mapped_column(String(50), index=True)

# This creates a custom-named index on the SAME column:
__table_args__ = (
    Index("idx_documents_status", "status"),
)
```

Pick one. We use explicit `__table_args__` indexes with descriptive names
and omit `index=True` on the column.

## References

- [Alembic autogenerate docs — render_item](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#affecting-the-rendering-of-types-themselves)
- [pgvector-python issue](https://github.com/pgvector/pgvector-python/issues/43)
