from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Branch, BranchIngredient, Ingredient, IngredientGroup


CUSTOM_DONUT_PRICE = Decimal("150.00")


def _localized(value, field: str, language: str) -> str:
    primary = getattr(value, f"{field}_en" if language == "en" else field, None)
    alternate = getattr(value, field if language == "en" else f"{field}_en", None)
    return primary or alternate or ""


def _error(message: str, language: str) -> str:
    if language != "ua":
        return message
    translations = {
        "Invalid custom donut selections": "Некоректний вибір інгредієнтів.",
        "Invalid custom donut ingredient": "Некоректний інгредієнт.",
        "Select ingredients for your custom donut": "Оберіть інгредієнти для власного пончика.",
    }
    return translations.get(message, message)


def custom_donut_catalog(
    session: Session,
    branch: Branch,
    language: str,
) -> list[dict]:
    rows = session.execute(
        select(IngredientGroup, Ingredient, BranchIngredient)
        .outerjoin(Ingredient, IngredientGroup.id == Ingredient.group_id)
        .outerjoin(
            BranchIngredient,
            (BranchIngredient.ingredient_id == Ingredient.id)
            & (BranchIngredient.branch_id == branch.id),
        )
        .order_by(IngredientGroup.id, Ingredient.id)
    ).all()

    groups_by_id: dict[int, dict] = {}
    for group, ingredient, availability in rows:
        group_data = groups_by_id.setdefault(
            group.id,
            {
                "id": group.id,
                "name": _localized(group, "name", language),
                "max_selections": group.max_selections,
                "is_mandatory": group.is_mandatory,
                "ingredients": [],
            },
        )
        if ingredient is None:
            continue
        group_data["ingredients"].append(
            {
                "id": ingredient.id,
                "name": _localized(ingredient, "name", language),
                "description": _localized(ingredient, "description", language),
                "is_available": bool(
                    ingredient.is_active
                    and availability is not None
                    and availability.is_available
                ),
            }
        )

    return list(groups_by_id.values())


def validate_custom_donut(
    session: Session,
    branch: Branch,
    ingredient_ids: list,
    language: str,
) -> list[Ingredient]:
    if not isinstance(ingredient_ids, list):
        raise ValueError(_error("Invalid custom donut selections", language))

    seen: set[int] = set()
    for ingredient_id in ingredient_ids:
        if (
            isinstance(ingredient_id, bool)
            or not isinstance(ingredient_id, int)
            or ingredient_id <= 0
            or ingredient_id in seen
        ):
            raise ValueError(_error("Invalid custom donut ingredient", language))
        seen.add(ingredient_id)

    catalog = custom_donut_catalog(session, branch, language)
    groups_by_id = {group["id"]: group for group in catalog}
    ingredients_by_id = {
        ingredient["id"]: (group, ingredient)
        for group in catalog
        for ingredient in group["ingredients"]
    }

    if not seen.issubset(ingredients_by_id):
        raise ValueError(_error("Invalid custom donut ingredient", language))

    selected_by_group: dict[int, int] = {}
    for ingredient_id in seen:
        group, ingredient = ingredients_by_id[ingredient_id]
        if not ingredient["is_available"]:
            if language == "ua":
                raise ValueError(f"{ingredient['name']} немає в цій філії.")
            raise ValueError(f"{ingredient['name']} is unavailable at this branch")
        selected_by_group[group["id"]] = selected_by_group.get(group["id"], 0) + 1

    for group_id, group in groups_by_id.items():
        count = selected_by_group.get(group_id, 0)
        if group["is_mandatory"] and count == 0:
            if language == "ua":
                raise ValueError(f"Оберіть варіант у групі «{group['name']}».")
            raise ValueError(f"{group['name']} requires a selection")
        if count > group["max_selections"]:
            if language == "ua":
                raise ValueError(
                    f"У групі «{group['name']}» можна обрати не більше "
                    f"{group['max_selections']} варіантів."
                )
            raise ValueError(f"{group['name']} allows at most {group['max_selections']} selections")

    if not seen:
        raise ValueError(
            _error("Select ingredients for your custom donut", language)
        )

    ingredients = session.scalars(
        select(Ingredient)
        .options(joinedload(Ingredient.group))
        .where(Ingredient.id.in_(seen))
        .order_by(Ingredient.id)
    ).all()
    return ingredients
