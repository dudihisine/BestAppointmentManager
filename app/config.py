"""
Configuration management using environment variables.
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Twilio WhatsApp Configuration
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg2://app:app@localhost:5432/scheduler")
    
    # Redis Configuration
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Application Configuration
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    timezone_default: str = os.getenv("TIMEZONE_DEFAULT", "Asia/Jerusalem")
    
    # Development/Debug
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
