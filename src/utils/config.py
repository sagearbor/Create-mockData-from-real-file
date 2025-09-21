"""Configuration management for the BYOD Synthetic Data Generator."""

import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Azure Configuration
    azure_tenant_id: Optional[str] = Field(default=None, env="AZURE_TENANT_ID")
    azure_client_id: Optional[str] = Field(default=None, env="AZURE_CLIENT_ID")
    azure_client_secret: Optional[str] = Field(default=None, env="AZURE_CLIENT_SECRET")
    
    # Azure OpenAI Configuration
    azure_openai_endpoint: Optional[str] = Field(default=None, env="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: Optional[str] = Field(default=None, env="AZURE_OPENAI_API_KEY")
    azure_openai_chat_deployment: str = Field(default="gpt-4", env="AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
    azure_openai_embedding_deployment: str = Field(default="text-embedding-ada-002", env="AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
    azure_openai_api_version: str = Field(default="2024-02-01", env="AZURE_OPENAI_API_VERSION")
    
    # Azure Storage Configuration
    azure_storage_connection_string: Optional[str] = Field(default=None, env="AZURE_STORAGE_CONNECTION_STRING")
    blob_storage_container_name: str = Field(default="synthetic-data-uploads", env="BLOB_STORAGE_CONTAINER_NAME")
    
    # Azure Cosmos DB Configuration
    cosmos_db_endpoint: Optional[str] = Field(default=None, env="COSMOS_DB_ENDPOINT")
    cosmos_db_key: Optional[str] = Field(default=None, env="COSMOS_DB_KEY")
    cosmos_db_database_name: str = Field(default="SyntheticData", env="COSMOS_DB_DATABASE_NAME")
    cosmos_db_container_name: str = Field(default="ProgramCatalog", env="COSMOS_DB_CONTAINER_NAME")
    
    # Azure AI Search Configuration
    azure_search_endpoint: Optional[str] = Field(default=None, env="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: Optional[str] = Field(default=None, env="AZURE_SEARCH_API_KEY")
    azure_search_index_name: str = Field(default="program-vectors", env="AZURE_SEARCH_INDEX_NAME")
    
    # Application Settings
    generator_version: str = Field(default="1.0", env="GENERATOR_VERSION")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    environment: str = Field(default="local", env="ENVIRONMENT")
    app_port: int = Field(default=8201, env="APP_PORT")
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")

    # CORS Security Settings
    allowed_origins: Optional[str] = Field(default=None, env="ALLOWED_ORIGINS")
    
    # Local Storage Settings
    use_local_storage: bool = Field(default=True, env="USE_LOCAL_STORAGE")
    local_storage_path: str = Field(default="./data/local_storage", env="LOCAL_STORAGE_PATH")
    local_cache_path: str = Field(default="./data/cache", env="LOCAL_CACHE_PATH")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"
        
    def is_local_mode(self) -> bool:
        """Check if running in local mode."""
        return self.environment == "local" or self.use_local_storage
    
    def ensure_local_directories(self):
        """Create local directories if they don't exist."""
        if self.is_local_mode():
            Path(self.local_storage_path).mkdir(parents=True, exist_ok=True)
            Path(self.local_cache_path).mkdir(parents=True, exist_ok=True)
            Path("./data/samples").mkdir(parents=True, exist_ok=True)
            Path("./logs").mkdir(parents=True, exist_ok=True)

    def get_allowed_origins(self) -> List[str]:
        """Get list of allowed origins for CORS based on environment."""
        # If explicitly set in environment, use that
        if self.allowed_origins:
            return [origin.strip() for origin in self.allowed_origins.split(",")]

        # Otherwise, use defaults based on environment
        if self.environment == "production":
            # Production: Only allow production URLs
            return [
                "https://byod-synthetic-data-service.azurewebsites.net",
                # Add your production domain here when available
            ]
        elif self.environment == "development":
            # Development: Allow dev URLs
            return [
                "https://byod-synthetic-data-service-dev.azurewebsites.net",
                "http://localhost:8201",
                "http://localhost:3000",
            ]
        else:  # local
            # Local development: Allow localhost variations and WSL/SSH scenarios
            return [
                "http://localhost:8201",
                "http://localhost:3000",
                "http://127.0.0.1:8201",
                "http://127.0.0.1:3000",
                "http://0.0.0.0:8201",  # WSL binding
                "http://0.0.0.0:3000",
                # Add your VM's IP if it's static, or use ALLOWED_ORIGINS env var
                # "http://your-vm-ip:8201",
                # Port forwarding scenarios (add as needed)
                "http://localhost:8080",  # Common forwarded port
                "http://localhost:8000",  # Another common port
            ]


# Global settings instance
settings = Settings()
settings.ensure_local_directories()