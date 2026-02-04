import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.datasource import (
    DatasourceCreate,
    DatasourceResponse,
    DatasourceTestResponse,
    NaturalLanguageQuery,
    SchemaResponse,
)

router = APIRouter()


@router.post(
    "/bots/{bot_id}/datasources",
    response_model=DatasourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_datasource(
    bot_id: uuid.UUID,
    data: DatasourceCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    """Add a new database connection for a bot."""
    # TODO: implement via DBConnectorService
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.get("/bots/{bot_id}/datasources", response_model=list[DatasourceResponse])
async def list_datasources(bot_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """List all database connections for a bot."""
    # TODO: implement
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.post("/datasources/{ds_id}/test", response_model=DatasourceTestResponse)
async def test_datasource(ds_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """Test a database connection."""
    # TODO: implement
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.post("/datasources/{ds_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_datasource(ds_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """Sync schema + sample data to the vector store."""
    # TODO: implement
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.get("/datasources/{ds_id}/schema", response_model=SchemaResponse)
async def get_datasource_schema(ds_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """View the extracted schema for a database connection."""
    # TODO: implement
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.delete("/datasources/{ds_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datasource(ds_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """Remove a database connection and its chunks."""
    # TODO: implement
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")


@router.post("/bots/{bot_id}/query-db")
async def query_database(
    bot_id: uuid.UUID,
    data: NaturalLanguageQuery,
    db: DBSession,
    current_user: CurrentUser,
):
    """Natural language -> SQL -> answer (live query against connected DB)."""
    # TODO: implement via Text2SQLService
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Coming soon")
