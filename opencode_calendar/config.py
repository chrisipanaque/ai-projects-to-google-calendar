import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

env_path = find_dotenv(usecwd=True)
if not env_path:
    env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DEFAULT_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def str_or_none(val):
    return val if val and val.strip() else None


def get_config():
    tz_name = os.getenv("TIMEZONE", "").strip()
    return {
        "db_path": os.path.expanduser(
            os.getenv("OPENCODE_DB_PATH", DEFAULT_DB_PATH)
        ),
        "google_credentials_path": str_or_none(
            os.getenv("GOOGLE_CREDENTIALS_PATH")
        ),
        "google_token_path": os.path.expanduser(
            os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        ),
        "github_token": str_or_none(os.getenv("GITHUB_TOKEN")),
        "github_model": os.getenv("GITHUB_MODEL", "gpt-4o-mini"),
        "timezone": tz_name if tz_name else None,
    }
