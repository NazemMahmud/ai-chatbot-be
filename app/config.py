from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI-Chatbot"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-to-a-random-string-min-32-chars"
    API_URL: str = "http://localhost:8000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/chatbot"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Storage - "local" or "minio"
    STORAGE_TYPE: str = "local"
    STORAGE_LOCAL_PATH: str = "./uploads"

    # MinIO/S3 (only needed if STORAGE_TYPE=minio)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_LLM_MODEL: str = "llama3.2:3b"

    # Embedding dimensions (nomic-embed-text = 768, other models may vary)
    EMBED_DIMENSIONS: int = 768

    # Document Parser: "simple" or "docling"
    DEFAULT_PARSER_TYPE: str = "simple"

    # Chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # Worker
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600  # 1 hour max per job

    # LLM Chat-bot Settings (used globally, not per-bot)
    # LLM_TEMPERATURE: float = 0.7
    # LLM_MAX_TOKENS: int = 1024
    LLM_SYSTEM_PROMPT: str = "You are a helpful AI assistant. Answer questions based on the provided context."

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()