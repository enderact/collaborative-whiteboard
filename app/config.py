from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongo_db: str = "whiteboard"
    redis_url: str = "redis://localhost:6379/0"
    snapshot_interval: int = 500
    # Upper bound on strokes replayed in the initial socket message. Rooms above
    # this size need a snapshot to be loaded in full.
    max_initial_strokes: int = 3000

    # Identifies this process in pub/sub messages so the UI can tell which
    # backend instance served a client during the multi-instance demo.
    instance_id: str = "wb-1"


settings = Settings()
