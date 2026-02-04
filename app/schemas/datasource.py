import uuid
from datetime import datetime

from pydantic import BaseModel


class DatasourceCreate(BaseModel):
    name: str
    db_type: str  # 'postgres', 'mysql', 'sqlite'
    host: str
    port: int
    database: str
    username: str
    password: str


class DatasourceResponse(BaseModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    name: str
    db_type: str
    status: str
    schema_cache: dict | None
    last_synced_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasourceTestResponse(BaseModel):
    success: bool
    message: str


class SchemaResponse(BaseModel):
    tables: dict  # table_name -> list of columns


class NaturalLanguageQuery(BaseModel):
    question: str
