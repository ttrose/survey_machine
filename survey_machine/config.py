from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    admin_api_key: str
    database_url: str = "sqlite:///data/survey-machine.sqlite3"
    cors_origins: tuple[str, ...] = ()
    secure_cookies: bool = False
    serve_ui: bool = True

    def __post_init__(self):
        if len(self.admin_api_key) < 32 or self.admin_api_key.startswith("replace-with-"):
            raise ValueError("Set ADMIN_API_KEY to a random secret of at least 32 characters. Run scripts/setup_dev.py for local setup.")

    @classmethod
    def from_environment(cls):
        import os

        return cls(
            admin_api_key=os.environ.get("ADMIN_API_KEY", ""),
            database_url=os.environ.get("DATABASE_URL", "sqlite:///data/survey-machine.sqlite3"),
            cors_origins=tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()),
            secure_cookies=os.environ.get("SECURE_COOKIES", "false").lower() == "true",
            serve_ui=os.environ.get("SERVE_UI", "true").lower() == "true",
        )
