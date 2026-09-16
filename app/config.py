from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str
    MODEL_SIZE: str = "small"  # tiny/base/small/medium ; для RU лучше small как минимум
    COMPUTE_TYPE: str = "int8"  # int8 для CPU, float16 для GPU
    MAX_DURATION_SEC: int = 300  # 5 мин
    TMP_DIR: str = "/tmp/voices"


settings = Settings()
