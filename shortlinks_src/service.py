"""
Core logic for shortlinks, plus the services other modules can use.

Services registered on the backbone (see main.py):

- ``shortlinks.get_by_code(code) -> LinkInfo | None``
- ``shortlinks.add_visit_listener(name, fn)``: ``fn(event: VisitEvent)`` is called
  (sync or async) after every redirect. Registering the same name again replaces
  the previous listener, so module reloads don't double-count.
- ``shortlinks.remove_visit_listener(name)``
"""
import inspect
import logging
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from chacc_api.database import async_session
from sqlalchemy import select

from .models import Link

logger = logging.getLogger("shortlinks")

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 6


def generate_code(length: int = CODE_LENGTH) -> str:
    """Random base62 code, e.g. 'x7Kp2Q'."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@dataclass(frozen=True)
class LinkInfo:
    """Read-only view of a link, safe to hand to other modules."""

    id: int
    code: str
    target_url: str
    hits: int
    created_at: datetime


@dataclass(frozen=True)
class VisitEvent:
    """What listeners receive when someone follows a short link."""

    link_id: int
    code: str
    target_url: str
    user_agent: str | None
    referer: str | None
    client_ip: str | None
    visited_at: datetime


def to_info(link: Link) -> LinkInfo:
    return LinkInfo(
        id=link.id,
        code=link.code,
        target_url=link.target_url,
        hits=link.hits or 0,
        created_at=link.created_at,
    )


async def get_by_code(code: str) -> LinkInfo | None:
    async with async_session() as db:
        link = (
            await db.execute(select(Link).where(Link.code == code, Link.deleted_at.is_(None)))
        ).scalar_one_or_none()
        return to_info(link) if link else None


# --- Visit listeners ---

Listener = Callable[[VisitEvent], Any | Awaitable[Any]]
_listeners: dict[str, Listener] = {}


def add_visit_listener(name: str, fn: Listener) -> None:
    _listeners[name] = fn
    logger.info(f"shortlinks: visit listener '{name}' registered.")


def remove_visit_listener(name: str) -> None:
    _listeners.pop(name, None)


def listener_names() -> list[str]:
    return sorted(_listeners)


async def notify_visit(event: VisitEvent) -> None:
    """Call every listener. A failing listener is logged and never breaks the others."""
    for name, fn in list(_listeners.items()):
        try:
            result = fn(event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001
            logger.exception(f"shortlinks: visit listener '{name}' failed.")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
