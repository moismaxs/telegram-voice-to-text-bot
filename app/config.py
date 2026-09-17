from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str
    MODEL_SIZE: str = "small"  # tiny/base/small/medium ; для RU лучше small как минимум
    COMPUTE_TYPE: str = "int8"  # int8 для CPU, float16 для GPU
    MAX_DURATION_SEC: int = 300  # 5 мин
    TMP_DIR: str = "/tmp/voices"
    # STT-бэкенд: local (faster-whisper на своём CPU, ~1ГБ RAM)
    # или groq (Whisper API, ~200МБ RAM, нужен GROQ_API_KEY с console.groq.com)
    STT_PROVIDER: str = "local"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "whisper-large-v3-turbo"
    # через запятую, например "123456789". Пусто — /stats закрыт для всех.
    ADMIN_IDS: str = ""
    # Пусто — авто: /data/voices.db если есть /data, иначе voices.db рядом.
    DB_PATH: str = ""
    # Ключ TeleAds (панель teleads.pro). Пусто — реклама отключена, бот работает как раньше.
    TELEADS_API_KEY: str = ""

    def admin_ids(self) -> set[int]:
        return {
            int(x.strip()) for x in self.ADMIN_IDS.split(",")
            if x.strip().isdigit()
        }


settings = Settings()
