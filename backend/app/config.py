from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    data_dir: str = "/app/data"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_collection: str = "prescriptions"

settings = Settings()