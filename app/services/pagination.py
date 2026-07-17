import base64
from dataclasses import dataclass
from typing import Literal, TypeVar

from fastapi import Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.schemas.pagination import CursorPage, Page

ModelT = TypeVar("ModelT")


@dataclass(frozen=True)
class OffsetPaginationParams:
    limit: int
    offset: int
    sort: str | None
    order: Literal["asc", "desc"]
    q: str | None


def get_offset_pagination(
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    sort: str | None = Query(None, description="Field to sort by"),
    order: Literal["asc", "desc"] = Query("asc", description="Sort direction"),
    q: str | None = Query(None, description="Free-text search term"),
) -> OffsetPaginationParams:
    return OffsetPaginationParams(
        limit=limit, offset=offset, sort=sort, order=order, q=q
    )


def apply_sort(
    statement: Select,
    model: type[ModelT],
    params: OffsetPaginationParams,
    allowed_fields: set[str],
    default_field: str = "id",
) -> Select:
    field_name = params.sort if params.sort in allowed_fields else default_field
    column = getattr(model, field_name)
    return statement.order_by(column.desc() if params.order == "desc" else column.asc())


def apply_search(
    statement: Select,
    model: type[ModelT],
    params: OffsetPaginationParams,
    search_fields: list[str],
) -> Select:
    if not params.q or not search_fields:
        return statement

    conditions = [
        getattr(model, field).ilike(f"%{params.q}%") for field in search_fields
    ]
    return statement.where(or_(*conditions))


def paginate_offset(
    db: Session, statement: Select, params: OffsetPaginationParams
) -> Page:
    count_statement = select(func.count()).select_from(statement.subquery())
    total = db.scalar(count_statement) or 0

    items = list(
        db.scalars(statement.limit(params.limit).offset(params.offset))
    )

    return Page(
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
        has_more=params.offset + len(items) < total,
    )


def encode_cursor(value: int) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid cursor") from exc


@dataclass(frozen=True)
class CursorPaginationParams:
    cursor: str | None
    limit: int
    q: str | None


def get_cursor_pagination(
    cursor: str | None = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    q: str | None = Query(None, description="Free-text search term"),
) -> CursorPaginationParams:
    return CursorPaginationParams(cursor=cursor, limit=limit, q=q)


def paginate_cursor(
    db: Session,
    statement: Select,
    model: type[ModelT],
    params: CursorPaginationParams,
) -> CursorPage:
    if params.cursor is not None:
        last_id = decode_cursor(params.cursor)
        statement = statement.where(model.id > last_id)

    statement = statement.order_by(model.id.asc()).limit(params.limit + 1)

    rows = list(db.scalars(statement))
    has_more = len(rows) > params.limit
    items = rows[: params.limit]

    next_cursor = encode_cursor(items[-1].id) if has_more and items else None

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
