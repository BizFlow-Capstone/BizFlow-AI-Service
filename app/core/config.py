from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is read from environment variables (or .env file).
    pydantic-settings validates types at startup — missing required vars
    raise a clear error before the app accepts any requests.
    """

    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",          # ignore .NET-specific vars in the shared .env files
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
    # Google Cloud STT (primary Speech-to-Text provider)
    # Path to the Google service-account JSON key file.
    # Set GOOGLE_APPLICATION_CREDENTIALS in the environment or .env file.
    # -------------------------------------------------------------------------
    google_application_credentials: str = ""

    # -------------------------------------------------------------------------
    # ChromaDB (in-process vector store for RAG)
    # -------------------------------------------------------------------------
    chroma_persist_dir: str = "./chroma_data"

    # -------------------------------------------------------------------------
    # Internal security
    # The BizFlow .NET API must pass this secret in the X-Internal-Secret header
    # for every request to the AI Service (container-to-container only).
    # -------------------------------------------------------------------------
    internal_api_secret: str = "change_me_in_production"

    # -------------------------------------------------------------------------
    # Service
    # -------------------------------------------------------------------------
    debug: bool = False


settings = Settings()
