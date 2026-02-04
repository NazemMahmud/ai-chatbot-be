from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models once at startup, release on shutdown."""
    # Embedding model (HuggingFace path)
    if settings.EMBED_PROVIDER == "huggingface":
        from sentence_transformers import SentenceTransformer

        app.state.embed_model = SentenceTransformer(settings.EMBED_MODEL_NAME)

    # Text2SQL model (only if DB feature enabled)
    if settings.ENABLE_DB_CONNECTOR and settings.SQL_PROVIDER == "huggingface":
        from transformers import AutoModelForCausalLM, AutoTokenizer

        app.state.sql_tokenizer = AutoTokenizer.from_pretrained(settings.SQL_MODEL_NAME)
        app.state.sql_model = AutoModelForCausalLM.from_pretrained(
            settings.SQL_MODEL_NAME, torch_dtype="auto", device_map="auto"
        )

    yield

    # Cleanup on shutdown
    if hasattr(app.state, "embed_model"):
        del app.state.embed_model
    if hasattr(app.state, "sql_model"):
        del app.state.sql_model


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register routers ---
from app.api.auth import router as auth_router  # noqa: E402
from app.api.bots import router as bots_router  # noqa: E402
from app.api.chat import router as chat_router  # noqa: E402
from app.api.datasources import router as datasources_router  # noqa: E402
from app.api.documents import router as documents_router  # noqa: E402
from app.api.widget import router as widget_router  # noqa: E402

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(bots_router, prefix="/api", tags=["bots"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(datasources_router, prefix="/api", tags=["datasources"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(widget_router, prefix="/api/widget", tags=["widget"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
