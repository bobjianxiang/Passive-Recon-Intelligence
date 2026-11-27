from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Passive Reconnaissance Intelligence System"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str
    APP_ENV: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
