from app.config import SessionLocal
from sqlalchemy import select
from decimal import Decimal

from app.models import (
    Branch,
    BranchProduct,
    IngredientGroup,
    Ingredient,
    Product,
    ProductIngredient,
)

from app.seed_data import (
    BRANCHES,
    INGREDIENT_GROUPS,
    INGREDIENTS,
    PRODUCTS,
    RECIPES,
    BRANCH_PRODUCT_ASSORTMENTS,
    OTHER_BRANCH_PRODUCT_ASSORTMENTS,
)


def seed_database(session):
    seed_catalog(session)
    seed_branches(session)
    session.flush()
    seed_branch_products(session)


def seed_recipes(session, products, ingredients):
    for product_name, recipe in RECIPES.items():
        product = products[product_name]

        for (
            ingredient_name,
            default_quantity,
            max_quantity,
            unit,
            is_changeable,
        ) in recipe:

            ingredient = ingredients[ingredient_name]

            recipe_item = session.get(
                ProductIngredient,
                (product.id, ingredient.id),
            )

            values = {
                "default_quantity": Decimal(default_quantity),
                "max_quantity": Decimal(max_quantity),
                "unit": unit,
                "is_changeable": is_changeable,
            }

            if recipe_item is None:
                recipe_item = ProductIngredient(
                    product_id=product.id,
                    ingredient_id=ingredient.id,
                    **values,
                )
                session.add(recipe_item)
            else:
                for key, value in values.items():
                    setattr(recipe_item, key, value)


def seed_catalog(session):
    groups = {}

    for data in INGREDIENT_GROUPS:
        group = session.scalar(
            select(IngredientGroup).where(
                IngredientGroup.name == data["name"]
            )
        )

        if group is None:
            group = IngredientGroup(**data)
            session.add(group)
        else:
            group.max_selections = data["max_selections"]

        groups[data["name"]] = group

    session.flush()

    ingredients = {}

    for data in INGREDIENTS:
        group = groups[data["group"]]

        ingredient = session.scalar(
            select(Ingredient).where(
                Ingredient.name == data["name"]
            )
        )

        values = {
            "description": data["description"],
            "group_id": group.id,
            "extra_price": Decimal(data["extra_price"]),
            "is_active": True,
        }

        if ingredient is None:
            ingredient = Ingredient(
                name=data["name"],
                **values,
            )
            session.add(ingredient)
        else:
            for key, value in values.items():
                setattr(ingredient, key, value)

        ingredients[data["name"]] = ingredient

    session.flush()

    products = {}

    for data in PRODUCTS:
        product = session.scalar(
            select(Product).where(
                Product.name == data["name"]
            )
        )

        values = {
            "description": data["description"],
            "base_price": Decimal(data["base_price"]),
            "calories": data["calories"],
            "image_url": data["image_url"],
            "is_active": True,
        }

        if product is None:
            product = Product(
                name=data["name"],
                **values,
            )
            session.add(product)
        else:
            for key, value in values.items():
                setattr(product, key, value)

        products[data["name"]] = product

    session.flush()

    seed_recipes(session, products, ingredients)

def seed_branches(session):
    for data in BRANCHES:
        branch = session.scalar(
            select(Branch).where(Branch.code == data["code"])
        )

        if branch is None:
            session.add(Branch(**data))


def seed_branch_products(session):
    branches = session.scalars(
        select(Branch).order_by(Branch.code)
    ).all()
    active_products = {
        product.name: product
        for product in session.scalars(
            select(Product).where(Product.is_active.is_(True))
        ).all()
    }
    existing_links = set(
        session.execute(
            select(BranchProduct.branch_id, BranchProduct.product_id)
        ).all()
    )
    other_branch_index = 0

    for branch in branches:
        assortment = BRANCH_PRODUCT_ASSORTMENTS.get(branch.code)
        if assortment is None:
            assortment = OTHER_BRANCH_PRODUCT_ASSORTMENTS[
                other_branch_index % len(OTHER_BRANCH_PRODUCT_ASSORTMENTS)
            ]
            other_branch_index += 1

        for product_name, is_available, price in assortment:
            product = active_products.get(product_name)
            if product is None:
                raise ValueError(
                    f"Branch assortment references missing or inactive product: {product_name}"
                )

            link_key = (branch.id, product.id)
            if link_key in existing_links:
                continue

            session.add(
                BranchProduct(
                    branch_id=branch.id,
                    product_id=product.id,
                    is_available=is_available,
                    price=Decimal(price) if price is not None else None,
                )
            )
            existing_links.add(link_key)


if __name__ == "__main__":
    with SessionLocal() as session:
        try:
            seed_database(session)
            session.commit()
            print("Data seeded successfully!")
        except Exception:
            session.rollback()
            raise