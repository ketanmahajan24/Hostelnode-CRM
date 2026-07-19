"""
Central application configuration.
All values are loaded from environment variables / .env file.
NEVER hardcode real secrets here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://88.222.242.183:27017"
    mongo_db_name: str = "hostelnode_crm"

    # Meta WhatsApp Cloud API
    wa_token: str = ""
    wa_phone_id: str = ""
    wa_business_account_id: str = ""
    wa_verify_token: str = ""
    wa_api_version: str = "v20.0"

    # App
    app_secret_key: str = "dev-secret-change-me"
    upload_dir: str = "static/uploads"
    max_upload_mb: int = 25

    # Auth / sessions
    session_cookie_name: str = "hostelnode_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # Display timezone for timestamps shown in the UI (storage stays UTC)
    display_timezone: str = "Asia/Kolkata"

    # The publicly reachable base URL of THIS server (e.g. https://crm.hostelnode.com
    # or https://your-vps-ip:8000 if no domain yet). Required so uploaded template
    # media (images/PDFs/videos) can be turned into an absolute public link that
    # Meta's servers can actually fetch — a relative path like /static/... is not
    # enough, Meta needs the full https:// URL.
    public_base_url: str = "http://localhost:8000"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.wa_api_version}/{self.wa_phone_id}"


settings = Settings()
