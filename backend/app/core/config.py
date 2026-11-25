from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 定位项目根目录下的 .env 文件，确保无论从根目录还是 backend 目录启动都能正确加载
ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """系统全局配置类，从环境变量及 .env 文件读取配置项。"""

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_matrix_hub"
    FERNET_KEY: str = ""

    AI_API_BASE: str = "https://api.openai.com/v1"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取缓存后的全局配置实例。"""
    return Settings()


settings = get_settings()

