"""
Database connector service — connects to external databases provided by the user,
reads schema and data for RAG indexing.

This is part of Group C (Database Query APIs) and should be implemented
after Groups A and B are working.
"""

import sqlalchemy
from sqlalchemy import inspect, text


class DBConnector:
    SUPPORTED_DRIVERS = {
        "postgres": "postgresql+asyncpg",
        "mysql": "mysql+aiomysql",
        "sqlite": "sqlite+aiosqlite",
    }

    SYNC_DRIVERS = {
        "postgres": "postgresql",
        "mysql": "mysql",
        "sqlite": "sqlite",
    }

    async def test_connection(self, db_type: str, connection_string: str) -> bool:
        """Verify the external DB is reachable."""
        driver = self.SUPPORTED_DRIVERS[db_type]
        engine = sqlalchemy.create_async_engine(f"{driver}://{connection_string}")
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        finally:
            await engine.dispose()

    def get_schema(self, db_type: str, connection_string: str) -> dict:
        """Extract table names, columns, types from an external DB."""
        driver = self.SYNC_DRIVERS[db_type]
        engine = sqlalchemy.create_engine(f"{driver}://{connection_string}")
        try:
            inspector = inspect(engine)
            schema = {}
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                schema[table_name] = [
                    {"name": col["name"], "type": str(col["type"])} for col in columns
                ]
            return schema
        finally:
            engine.dispose()

    async def sync_to_chunks(self, db_connection_id: str, bot_id: str, db):
        """
        Read DB schema + sample data -> create document chunks for RAG.

        Steps:
        1. Get connection config
        2. Extract schema as text description
        3. Optionally sample rows for context
        4. Chunk schema descriptions
        5. Generate embeddings
        6. Store in document_chunks with source_type="database"
        """
        # TODO: implement
        pass
