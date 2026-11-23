
from datetime import date 
from functools import lru_cache  # Import lru_cache to save the result of a function
from pydantic import Field # Import Field to define default values

# Import tools to manage application settings
from pydantic_settings import BaseSettings, SettingsConfigDict

# a class to store all application settings
class Settings(BaseSettings):

    # Tell Pydantic to read settings from the .env file
    # Ignore extra variables that are not defined in this class
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    
    mongodb_uri: str            # MongoDB connection address
    mongodb_db: str             # Name of the MongoDB database
    groq_api_key: str           # API key used to access Groq
    voyage_api_key: str         # API key used to access Voyage
    jwt_secret: str             # Secret key used for JWT tokens

    # Optional settings (they have default values)

    # List of frontend addresses allowed to communicate with the backend
    # If nothing is provided, use localhost:5173
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Optional date used for testing instead of the real current date
    # None means no date override
    today_override: date | None = None

    # Confirmation expiration time in seconds (2 minutes)
    confirm_ttl_s: int = 120


# Cache the result so we don't recreate Settings every time
@lru_cache
def get_settings() -> Settings:

    # Create and return the Settings object
    # Pydantic reads and validates the values from .env
    return Settings()


# Function used to get today's date
def get_today() -> date:

    # This is the only place in the project that reads the real date

    # Get the application settings
    s = get_settings()

    # If a date override exists, use it
    # Otherwise, return the real current date
    return s.today_override or date.today()
