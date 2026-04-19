from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI-Chatbot"
    APP_ENV: str = "development"
    DEBUG: bool = True
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

    # Embedding dimensions (nomic-embed-text = 768, mxbai-embed-large = 1024)
    EMBED_DIMENSIONS: int = 768

    # Embedding safety limits
    EMBED_MAX_INPUT_CHARS: int = 6000    # hard char truncation before sending to model
    EMBED_MAX_CONCURRENT: int = 4        # max parallel /api/embed requests
    EMBED_SHRINK_RETRIES: int = 4        # retries with halved text on context overflow
    EMBED_MIN_RETRY_CHARS: int = 200     # stop shrinking below this
    EMBED_TIMEOUT: float = 300.0         # seconds per embed HTTP request

    # Document upload
    # MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB max upload

    # Document Parser: "simple" or "docling"
    DEFAULT_PARSER_TYPE: str = "simple"

    # Chunking — "character" (fast, basic) or "semantic" (slower, smarter)
    CHUNKING_STRATEGY: str = "semantic"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # Semantic chunking settings (only used when CHUNKING_STRATEGY=semantic)
    SEMANTIC_SIMILARITY_PERCENTILE: float = 10.0  # breakpoint at bottom X% of similarities
    SEMANTIC_MIN_CHUNK_SIZE: int = 200   # minimum chars per semantic chunk
    SEMANTIC_MAX_CHUNK_SIZE: int = 2000  # maximum chars per semantic chunk
    SEMANTIC_MAX_SENTENCE_CHARS: int = 500   # hard limit per sentence before word-boundary split
    SEMANTIC_MAX_WINDOW_CHARS: int = 6000    # hard limit per sliding window sent to embedder

    # Worker
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600  # 1 hour max per job

    # JWT
    JWT_SECRET: str = "change-me-to-a-random-string-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # LLM Chat-bot Settings (used globally, not per-bot)
    # LLM_TEMPERATURE: float = 0.7
    # LLM_MAX_TOKENS: int = 1024
    LLM_SYSTEM_PROMPT: str = "You are a helpful AI assistant. Answer questions based on the provided context."

    # Separate smaller/faster model for document summary extraction during processing.
    # Uses OLLAMA_LLM_MODEL if not set.
    OLLAMA_SUMMARY_MODEL: str = ""

    # Ollama timeout (seconds) for LLM chat requests
    OLLAMA_TIMEOUT: float = 300.0

    # Hybrid retrieval tuning
    VECTOR_TOP_K: int = 50   # candidates from vector cosine search
    KEYWORD_TOP_K: int = 30  # candidates from keyword (tsvector) search
    RRF_K: int = 60          # RRF smoothing constant (standard value)

    # Reranker (flashrank cross-encoder, runs after RRF merge)
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL: str = "ms-marco-MiniLM-L-12-v2"
    RERANKER_TOP_N: int = 20  # keep top N chunks after reranking

    # Query Rewriting — LLM generates alternative search queries (multi-query retrieval)
    QUERY_REWRITE_ENABLED: bool = False
    QUERY_REWRITE_NUM_QUERIES: int = 3  # number of alternative queries to generate

    # Agentic RAG — retry retrieval with LLM-suggested queries on refusal
    AGENTIC_RAG_ENABLED: bool = False
    AGENTIC_RAG_MAX_RETRIES: int = 2  # max retry attempts on refusal

    # Metadata Extraction — LLM extracts entities/topics from chunks during processing
    METADATA_EXTRACTION_ENABLED: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()