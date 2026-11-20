from datetime import datetime

from chacc_api import ChaCCBaseModel
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Column, Integer, String


class Link(ChaCCBaseModel):
    """A short code that redirects to a target URL."""

    __tablename__ = "shortlinks_links"

    code = Column(String(32), unique=True, index=True, nullable=False)
    target_url = Column(String(2048), nullable=False)
    hits = Column(Integer, nullable=False, default=0, server_default="0")


# --- API schemas ---

CODE_PATTERN = r"^[A-Za-z0-9_-]{3,32}$"


class LinkCreate(BaseModel):
    url: HttpUrl = Field(..., description="The long URL to shorten (http or https).")
    code: str | None = Field(
        None,
        pattern=CODE_PATTERN,
        description="Optional custom code (3-32 chars: letters, digits, '-' or '_').",
        examples=["summer-sale"],
    )


class LinkResponse(BaseModel):
    code: str
    short_url: str
    target_url: str
    hits: int
    created_at: datetime
