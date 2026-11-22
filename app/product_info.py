"""Extra product information shown on the store and product pages.

Ideas borrowed from Kyiv pastry shops:
- Milk Bar marks cards with a "Bestseller" badge and lists shelf life and
  storage temperature on every cake page.
- Honey and others list allergens and dietary labels next to the composition.
- Milk Bar's "Potential crushes" block suggests similar desserts.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, OrderStatus, Product, ProductIngredient

BESTSELLER_LIMIT = 3
RELATED_LIMIT = 3

# Allergens matched by keywords in ingredient names (lower case). Kept in code
# so the catalogue needs no migration; owners can extend the table here.
ALLERGEN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dough", ("Gluten", "Eggs", "Milk")),
    ("cream", ("Milk",)),
    ("white chocolate", ("Milk", "Soy")),
    ("chocolate", ("Soy",)),
    ("choco", ("Soy",)),
    ("pistachio", ("Tree nuts",)),
    ("cookie", ("Gluten", "Eggs", "Milk")),
)

ALLERGEN_ORDER = ("Gluten", "Eggs", "Milk", "Soy", "Tree nuts")

STORAGE_NOTE = (
    "Best on the day it's baked. Keeps up to 24 hours in the fridge "
    "at +2…+6 °C. Warm it for 10 seconds in the microwave to bring "
    "back the softness."
)

KITCHEN_NOTE = (
    "All donuts are made in one kitchen that also handles nuts, gluten, "
    "milk, eggs and soy, so traces are possible."
)


def allergens_for(ingredient_names: Iterable[str]) -> list[str]:
    found: set[str] = set()
    for name in ingredient_names:
        lowered = name.casefold()
        for keyword, allergens in ALLERGEN_KEYWORDS:
            if keyword in lowered:
                found.update(allergens)
    return [allergen for allergen in ALLERGEN_ORDER if allergen in found]


def bestseller_ids(session: Session, limit: int = BESTSELLER_LIMIT) -> set[int]:
    """The most ordered donuts across all branches (cancelled orders excluded)."""
    sold = func.sum(OrderItem.quantity)
    rows = session.execute(
        select(OrderItem.product_id, sold)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            OrderItem.product_id.is_not(None),
            Order.status != OrderStatus.CANCELLED,
            Product.is_active.is_(True),
        )
        .group_by(OrderItem.product_id)
        .order_by(sold.desc(), OrderItem.product_id)
        .limit(limit)
    ).all()
    return {product_id for product_id, total in rows if total}


def related_products(
    session: Session,
    product: Product,
    *,
    allowed_ids: set[int] | None = None,
    limit: int = RELATED_LIMIT,
) -> list[Product]:
    """Other active donuts that share the most ingredients with this one.

    allowed_ids limits the suggestions to donuts the selected branch sells.
    """
    own_ingredients = {item.ingredient_id for item in product.recipe}

    candidates = session.scalars(
        select(Product).where(
            Product.is_active.is_(True),
            Product.id != product.id,
        )
    ).all()
    if allowed_ids is not None:
        candidates = [item for item in candidates if item.id in allowed_ids]
    if not candidates:
        return []

    recipe_rows = session.execute(
        select(ProductIngredient.product_id, ProductIngredient.ingredient_id).where(
            ProductIngredient.product_id.in_([item.id for item in candidates])
        )
    ).all()
    shared: dict[int, int] = {}
    for product_id, ingredient_id in recipe_rows:
        if ingredient_id in own_ingredients:
            shared[product_id] = shared.get(product_id, 0) + 1

    candidates.sort(key=lambda item: (-shared.get(item.id, 0), item.id))
    return candidates[:limit]
