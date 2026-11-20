from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chacc_api.database import get_async_db
from chacc_api.rate_limit import rate_limit

from .models import Link, LinkCreate, LinkResponse
from .service import VisitEvent, generate_code, listener_names, notify_visit, now_utc

router = APIRouter()

MAX_CODE_ATTEMPTS = 5


def _short_url(request: Request, code: str) -> str:
    return str(request.url_for("follow_link", code=code))


def _to_response(request: Request, link: Link) -> LinkResponse:
    return LinkResponse(
        code=link.code,
        short_url=_short_url(request, link.code),
        target_url=link.target_url,
        hits=link.hits or 0,
        created_at=link.created_at,
    )


async def _active_link(db: AsyncSession, code: str) -> Link:
    link = (
        await db.execute(select(Link).where(Link.code == code, Link.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No short link with code '{code}'.")
    return link


async def _code_taken(db: AsyncSession, code: str) -> bool:
    # Soft-deleted codes stay reserved, so an old printed link never points somewhere new.
    return (await db.execute(select(Link.id).where(Link.code == code))).first() is not None


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
@rate_limit("30/minute")
async def create_link(request: Request, body: LinkCreate, db: AsyncSession = Depends(get_async_db)):
    """Shorten a URL. Pass `code` to choose the short code yourself."""
    if body.code:
        if await _code_taken(db, body.code):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Code '{body.code}' is already taken.")
        code = body.code
    else:
        for _ in range(MAX_CODE_ATTEMPTS):
            code = generate_code()
            if not await _code_taken(db, code):
                break
        else:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not allocate a code.")

    link = Link(code=code, target_url=str(body.url), hits=0)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _to_response(request, link)


@router.get("", response_model=list[LinkResponse])
async def list_links(request: Request, db: AsyncSession = Depends(get_async_db)):
    """All active short links, newest first."""
    links = (
        await db.execute(
            select(Link).where(Link.deleted_at.is_(None)).order_by(Link.created_at.desc(), Link.id.desc())
        )
    ).scalars().all()
    return [_to_response(request, link) for link in links]


@router.get("/_listeners", include_in_schema=False)
async def get_listeners():
    """Which modules are listening to visits (handy to show linkstats plugging in)."""
    return {"listeners": listener_names()}


@router.get("/{code}/info", response_model=LinkResponse)
async def link_info(code: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Details of a short link, without redirecting."""
    return _to_response(request, await _active_link(db, code))


@router.get(
    "/{code}",
    name="follow_link",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    responses={307: {"description": "Redirect to the target URL"}, 404: {"description": "Unknown code"}},
)
async def follow_link(
    code: str,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    """Follow a short link: redirects to its target and tells visit listeners."""
    link = await _active_link(db, code)
    await db.execute(update(Link).where(Link.id == link.id).values(hits=Link.hits + 1))
    await db.commit()

    background.add_task(
        notify_visit,
        VisitEvent(
            link_id=link.id,
            code=link.code,
            target_url=link.target_url,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            client_ip=request.client.host if request.client else None,
            visited_at=now_utc(),
        ),
    )
    return RedirectResponse(link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(code: str, db: AsyncSession = Depends(get_async_db)):
    """Retire a short link. Its code stays reserved and its stats are kept."""
    link = await _active_link(db, code)
    link.deleted_at = now_utc()
    await db.commit()
