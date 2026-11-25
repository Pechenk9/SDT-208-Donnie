from app.config import SessionLocal
from sqlalchemy import or_, select
from decimal import Decimal

from app.models import (
    Branch,
    BranchIngredient,
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
    seed_branch_ingredients(session)
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
                # Existing recipes are business data. Re-running seeds must not
                # overwrite a catalogue administrator's recipe customization.
                continue


def seed_catalog(session):
    groups = {}

    for data in INGREDIENT_GROUPS:
        group = session.scalar(
            select(IngredientGroup).where(
                or_(
                    IngredientGroup.name == data["name"],
                    IngredientGroup.name == data["name_en"],
                    IngredientGroup.name_en == data["name_en"],
                )
            )
        )

        if group is None:
            group = IngredientGroup(**data)
            session.add(group)
        else:
            if group.name == data["name_en"]:
                group.name = data["name"]
            if not group.name_en:
                group.name_en = data["name_en"]
            group.is_mandatory = data["is_mandatory"]

        groups[data["name"]] = group
        groups[data["name_en"]] = group

    session.flush()

    ingredients = {}

    for data in INGREDIENTS:
        group = groups[data["group"]]

        ingredient = session.scalar(
            select(Ingredient).where(
                or_(
                    Ingredient.name == data["name"],
                    Ingredient.name == data["name_en"],
                    Ingredient.name_en == data["name_en"],
                )
            )
        )

        if ingredient is None:
            ingredient = Ingredient(
                name=data["name"],
                name_en=data["name_en"],
                description=data["description"],
                description_en=data["description_en"],
                group_id=group.id,
                extra_price=Decimal(data["extra_price"]),
                is_active=True,
            )
            session.add(ingredient)
        else:
            if ingredient.name == data["name_en"]:
                ingredient.name = data["name"]
            if ingredient.description == data["description_en"]:
                ingredient.description = data["description"]
            if not ingredient.name_en:
                ingredient.name_en = data["name_en"]
            if not ingredient.description_en:
                ingredient.description_en = data["description_en"]

        ingredients[data["name"]] = ingredient
        ingredients[data["name_en"]] = ingredient

    session.flush()

    products = {}

    for data in PRODUCTS:
        product = session.scalar(
            select(Product).where(
                or_(
                    Product.name == data["name"],
                    Product.name == data["name_en"],
                    Product.name_en == data["name_en"],
                )
            )
        )

        if product is None:
            product = Product(
                name=data["name"],
                name_en=data["name_en"],
                description=data["description"],
                description_en=data["description_en"],
                base_price=Decimal(data["base_price"]),
                calories=data["calories"],
                image_url=data["image_url"],
                is_active=True,
            )
            session.add(product)
        else:
            if product.name == data["name_en"]:
                product.name = data["name"]
            if product.description == data["description_en"]:
                product.description = data["description"]
            if not product.name_en:
                product.name_en = data["name_en"]
            if not product.description_en:
                product.description_en = data["description_en"]

        products[data["name"]] = product
        products[data["name_en"]] = product

    session.flush()

    seed_recipes(session, products, ingredients)

def seed_branches(session):
    for data in BRANCHES:
        branch = session.scalar(
            select(Branch).where(Branch.code == data["code"])
        )

        if branch is None:
            session.add(Branch(**data))
        else:
            if branch.city == data["city_en"]:
                branch.city = data["city"]
            if branch.address == data["address_en"]:
                branch.address = data["address"]
            if not branch.city_en:
                branch.city_en = data["city_en"]
            if not branch.address_en:
                branch.address_en = data["address_en"]


def seed_branch_products(session):
    branches = session.scalars(
        select(Branch).order_by(Branch.code)
    ).all()
    active_products = {}
    for product in session.scalars(
        select(Product).where(Product.is_active.is_(True))
    ).all():
        active_products[product.name] = product
        if product.name_en:
            active_products[product.name_en] = product
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


def seed_branch_ingredients(session):
    branches = session.scalars(
        select(Branch).order_by(Branch.id)
    ).all()
    ingredients = session.scalars(
        select(Ingredient).order_by(Ingredient.id)
    ).all()
    existing_links = set(
        session.execute(
            select(
                BranchIngredient.branch_id,
                BranchIngredient.ingredient_id,
            )
        ).all()
    )

    for branch in branches:
        for ingredient in ingredients:
            link_key = (branch.id, ingredient.id)
            if link_key in existing_links:
                continue

            session.add(
                BranchIngredient(
                    branch_id=branch.id,
                    ingredient_id=ingredient.id,
                    is_available=True,
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