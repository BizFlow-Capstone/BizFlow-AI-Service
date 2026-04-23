from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is read from environment variables (or .env file).
    Đọc từ file .env.dev của BizFlow-BE-Service (chung 1 file với BE).
    pydantic-settings validates types at startup — missing required vars
    raise a clear error before the app accepts any requests.
    """

    model_config = SettingsConfigDict(
        # Đọc từ file env chung của BE. Đường dẫn tương đối so với CWD khi
        # chạy uvicorn (từ thư mục BizFlow-AI-Service).
        # Docker: env vars được inject trực tiếp qua docker-compose environment:
        #         nên env_file không được dùng trong container.
        env_file="../BizFlow-BE-Service/.env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Database (SQLAlchemy URL — MySQL via PyMySQL)
    # -------------------------------------------------------------------------
    # Format: mysql+pymysql://<user>:<password>@<host>:<port>/<db>?charset=utf8mb4
    ai_db_url: str = "mysql+pymysql://admin:admin@localhost:3307/bizflow_db?charset=utf8mb4"

    # -------------------------------------------------------------------------
    # OpenAI
    # -------------------------------------------------------------------------
    openai_api_key: str

    # -------------------------------------------------------------------------
    # Google Cloud STT v2 (primary Speech-to-Text provider)
    # GOOGLE_APPLICATION_CREDENTIALS: path to service-account JSON key file.
    # GOOGLE_CLOUD_PROJECT: GCP project ID (required for v2 recognizer path).
    # -------------------------------------------------------------------------
    google_application_credentials: str = ""
    # Đọc FIREBASE_PROJECT_ID từ .env (chung với BE).
    # AliasChoices ưu tiên FIREBASE_PROJECT_ID trước, fallback GOOGLE_CLOUD_PROJECT nếu Docker override.
    google_cloud_project: str = Field(
        default="",
        validation_alias=AliasChoices("FIREBASE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
    )
    google_stt_model: str = "long"  # "long" | "chirp_2" | "latest_long"

    # -------------------------------------------------------------------------
    # ChromaDB (in-process vector store for RAG)
    # -------------------------------------------------------------------------
    chroma_persist_dir: str = "./chroma_data"
    embedding_model_name: str = "intfloat/multilingual-e5-small"

    # -------------------------------------------------------------------------
    # Vector search quality controls
    # -------------------------------------------------------------------------
    vector_fuzzy_threshold: float = 0.35
    vector_fuzzy_score_cutoff: int = 60

    # -------------------------------------------------------------------------
    # Internal security
    # The BizFlow .NET API must pass this secret in the X-Internal-Secret header
    # for every request to the AI Service (container-to-container only).
    # BE env dùng tên AI_SERVICE_INTERNAL_SECRET; Docker dùng INTERNAL_API_SECRET.
    # AliasChoices cho phép đọc cả hai tên.
    # -------------------------------------------------------------------------
    internal_api_secret: str = Field(
        default="supersecretkey",
        validation_alias=AliasChoices("INTERNAL_API_SECRET", "AI_SERVICE_INTERNAL_SECRET"),
    )

    # -------------------------------------------------------------------------
    # LLM — models
    # Override via env to switch model tier without touching code.
    # -------------------------------------------------------------------------
    llm_chat_model:   str = "gpt-4o-mini"   # used by chat()
    llm_vision_model: str = "gpt-4o"        # used by vision()

    # -------------------------------------------------------------------------
    # LLM — feature-specific temperatures
    # Each feature can be tuned independently via .env without a code deploy.
    #   extraction tasks (structured JSON)  → 0.0–0.2
    #   analytical text generation          → 0.2–0.4
    #   creative / open-ended explanation   → 0.4–0.7
    # -------------------------------------------------------------------------
    llm_draft_order_temperature: float = 0.1
    llm_draft_order_max_tokens:  int   = 1024

    llm_forecast_temperature: float = 0.2
    llm_forecast_max_tokens:  int   = 256

    llm_anomaly_temperature: float = 0.4
    llm_anomaly_max_tokens:  int   = 300

    # -------------------------------------------------------------------------
    # Service
    # -------------------------------------------------------------------------
    debug: bool = False


settings = Settings()
