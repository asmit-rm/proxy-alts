from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str
    OWNER_IDS: str
    SALES_LOG_CHAT_ID: str | None = None

    SUPPORT_USERNAME: str = "@revulet"
    FORCE_JOIN_1: str = "@proxydominates"
    FORCE_JOIN_2: str = "@noruleclub"
    FORCE_JOIN_3: str = "@vnumrates"
    UPI_ID: str = "proxyfxc@pytes"
    CURRENCY: str = "₹"

    # Telethon
    API_ID: int
    API_HASH: str

    @property
    def owner_ids(self) -> List[int]:
        return [int(x.strip()) for x in self.OWNER_IDS.split(",") if x.strip()]


settings = Settings()
