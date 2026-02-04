from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI-Chatbot"
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-to-a-random-string-min-32-chars"
    API_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/chatbot"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Storage
    STORAGE_TYPE: str = "minio"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "chatbot"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Embedding: "ollama" or "huggingface"
    EMBED_PROVIDER: str = "ollama"
    EMBED_MODEL_NAME: str = "nomic-embed-text"
    EMBED_DIMENSIONS: int = 768

    # Chat LLM (via Ollama)
    CHAT_MODEL_NAME: str = "smollm3:3b"
    CHAT_TEMPERATURE: float = 0.7

    # Document Parser: "simple" or "docling"
    PARSER_TYPE: str = "simple"

    # Text2SQL
    ENABLE_DB_CONNECTOR: bool = False
    SQL_PROVIDER: str = "ollama"
    SQL_MODEL_NAME: str = "sqlcoder:7b"

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60

    # JWT
    JWT_SECRET: str = "change-me-to-another-random-string"
    JWT_EXPIRY_HOURS: int = 24
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
