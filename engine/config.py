"""Business profiles and settings.

Brand details live in businesses.json, which is safe to commit. Gmail
credentials live in .env or the environment and never in the repo:

  TILING_GMAIL_ADDRESS    TILING_GMAIL_APP_PASSWORD
  ECOSHINE_GMAIL_ADDRESS  ECOSHINE_GMAIL_APP_PASSWORD

The prefix is the business "key" from businesses.json, upper-cased.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
DB_PATH = Path(os.environ.get("ENGINE_DB") or DATA_DIR / "engine.db")


@dataclass(frozen=True)
class Business:
    key: str
    name: str
    from_name: str
    brand_color: str
    tagline: str
    phone: str
    website: str
    address: str
    review_url: str
    booking_url: str
    daily_limit: int
    sender_name: str = ""  # who signs the emails, e.g. "Sam"

    @property
    def env_prefix(self) -> str:
        return self.key.upper()

    @property
    def gmail_address(self) -> str:
        return os.environ.get(f"{self.env_prefix}_GMAIL_ADDRESS", "").strip()

    @property
    def gmail_password(self) -> str:
        # Google displays app passwords in groups of four; spaces are not part of it.
        return os.environ.get(f"{self.env_prefix}_GMAIL_APP_PASSWORD", "").replace(" ", "")

    @property
    def configured(self) -> bool:
        return bool(self.gmail_address and self.gmail_password)

    @property
    def profile_gaps(self) -> list[str]:
        """Empty profile fields that templates or the footer rely on."""
        return [f for f in ("phone", "website", "address", "review_url", "booking_url")
                if not getattr(self, f)]

    def template_vars(self) -> dict[str, str]:
        return {
            "business_name": self.name,
            "sender_name": self.sender_name or f"The {self.name} team",
            "phone": self.phone,
            "phone_tel": self.phone.replace(" ", ""),
            "website": self.website,
            "address": self.address,
            "review_url": self.review_url,
            "booking_url": self.booking_url,
        }


def load_businesses() -> dict[str, Business]:
    raw = json.loads((ROOT / "businesses.json").read_text(encoding="utf-8"))
    return {b["key"]: Business(**b) for b in raw}


BUSINESSES = load_businesses()


def get_business(key: str) -> Business:
    try:
        return BUSINESSES[key]
    except KeyError:
        raise ValueError(f"unknown business {key!r}; expected one of: {', '.join(BUSINESSES)}")
