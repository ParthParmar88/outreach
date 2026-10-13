"""Products, scoped to the signed-in account."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from outreach.api.deps import CurrentUser, DbSession
from outreach.db.models.product import CrawlState
from outreach.db.repositories import products as repo
from outreach.schemas.product import (
    PlanOut,
    ProductCreate,
    ProductDetail,
    ProductOut,
    ProductUpdate,
)
from outreach.services import plan_service, product_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

#: Same message whether the product does not exist or belongs to somebody
#: else. Telling the two apart hands out a way to probe for other people's ids.
NOT_FOUND = "No product with that id."


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: CurrentUser,
    session: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> ProductOut:
    """
    Register a product and start reading its website.

    Returns immediately. The crawl runs in the background because it takes
    anywhere from ten seconds to a few minutes, and nobody should watch a
    spinner for that long.

    **201** a new product, and the crawl has started.
    **200** this account already had that domain, and nothing was re-read.
    """
    try:
        product, created = await product_service.get_or_create(session, payload, user.id)
    except product_service.ProductError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await session.commit()

    if created:
        background.add_task(product_service.run_crawl, product.id)
    else:
        response.status_code = status.HTTP_200_OK

    return ProductOut.model_validate(product)


@router.get("/{product_id}/plan", response_model=PlanOut)
async def get_plan(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> PlanOut:
    """
    The marketing plan for this product.

    **404** when there is none yet. The crawl has to finish first, because a
    plan written before the website has been read is generic advice.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    plan = plan_service.current_plan(product)
    if plan is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No plan yet. Generate one once the website has been read.",
        )

    return PlanOut(
        plan=plan,
        stale=plan_service.is_stale(product),
        made_at=product.plan_made_at,
    )


@router.post("/{product_id}/plan", status_code=status.HTTP_202_ACCEPTED)
async def make_plan(
    product_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    background: BackgroundTasks,
    force: bool = False,
) -> dict[str, str]:
    """
    Write the marketing plan. Returns immediately; poll GET for the result.

    Takes 20 to 40 seconds because it is a large model writing several
    paragraphs. Nothing happens if a current plan already exists, unless
    `force=true`.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    if product.state == CrawlState.CRAWLING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Still reading the website. Try again when it has finished.",
        )

    background.add_task(plan_service.ensure_plan, product.id, force)
    return {"status": "writing"}


@router.get("", response_model=list[ProductOut])
async def list_products(user: CurrentUser, session: DbSession) -> list[ProductOut]:
    """Everything this account owns, newest first. Feeds the product picker."""
    rows = await repo.list_for_user(session, user.id)
    return [ProductOut.model_validate(row) for row in rows]


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> ProductDetail:
    """Status and the page list. Poll this while the crawl is running."""
    product = await repo.get_owned_with_pages(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return ProductDetail.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    user: CurrentUser,
    session: DbSession,
) -> ProductOut:
    """
    Edit the name, what the product does, or what the owner wants.

    Until this existed the two fields the planner actually reads were
    write-once: set them wrong when creating the product and the only repair
    was to make a new one and re-crawl the same website. That is how an
    account ends up with three rows of the same name.

    Deliberately does **not** rewrite the plan. Editing the goal and
    re-planning are two decisions, and doing the second automatically means
    a typo correction silently spends a model call and replaces a plan
    somebody may have hand-edited. The response carries the new values, the
    plan's own `stale` flag turns true on its own - because both fields are
    hashed into it - and the plan screen already knows how to say so.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    # `exclude_unset` so "not mentioned" and "explicitly cleared" stay
    # different things: PATCH with {"goal": null} empties the goal, PATCH
    # without the key leaves it alone.
    changes = payload.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        # `name` is required in the model, so an empty one is a no-op rather
        # than a way to end up with a product that has no name.
        if field == "name" and not value:
            continue
        setattr(product, field, value)

    await session.flush()
    log.info("product.updated", product_id=str(product_id), fields=sorted(changes))
    return ProductOut.model_validate(product)


@router.get("/{product_id}/markdown", response_class=Response)
async def get_markdown(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    """
    The combined document, as a markdown file.

    This is the single file that later gets handed to the model so it
    understands what the product is and what it solves.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if not product.markdown:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Nothing has been read yet. The crawl is {product.state.value}.",
        )

    filename = f"{product.domain.replace('.', '-')}.md"
    return Response(
        content=product.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> None:
    """
    Forget a product and everything we read for it.

    Its pages go with it, because product_page is declared ON DELETE CASCADE.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    await session.delete(product)


@router.post("/{product_id}/recrawl", response_model=ProductOut)
async def recrawl_product(
    product_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    background: BackgroundTasks,
) -> ProductOut:
    """
    Read the website again.

    The only way a site is ever re-read. There is no schedule and no
    automatic refresh, by design.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    # A crawl past its own time limit is dead, not busy. Refusing it would
    # strand the row forever, since the server restart that killed it also
    # left it marked "crawling".
    if product.state == CrawlState.CRAWLING and not product_service.is_stale(product):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That crawl is already running. Wait for it to finish.",
        )

    await product_service.reset_for_recrawl(session, product)
    await session.commit()

    background.add_task(product_service.run_crawl, product.id)
    return ProductOut.model_validate(product)
