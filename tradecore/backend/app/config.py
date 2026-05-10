from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — no defaults; app fails fast if missing
    db_user: str
    db_password: str
    db_host: str
    db_name: str

    db_port: int = 5432
    ccxt_exchange: str = "binance"
    ccxt_api_key: str = ""
    ccxt_secret: str = ""
    ntfy_url: str = ""
    ntfy_token: str = ""
    trading_mode: str = "paper"
    app_version: str = "0.1.0"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
