from sqlalchemy import func, select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Base
from app.models import (
    Branch,
    BranchIngredient,
    Ingredient,
    IngredientGroup,
)
from app.seed import seed_database


def test_seed_database_fills_branch_ingredients_idempotently():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            branch = Branch(
                code="EXTRA-SEED-BRANCH",
                name="Extra Seed Branch",
                city="Kyiv",
                address="Extra address",
            )
            group = IngredientGroup(
                name="Extra Seed Group",
                max_selections=1,
            )
            ingredient = Ingredient(
                name="Extra Seed Ingredient",
                group=group,
                extra_price=0,
            )
            existing_association = BranchIngredient(
                branch=branch,
                ingredient=ingredient,
                is_available=False,
            )
            session.add_all([branch, group, ingredient, existing_association])
            session.commit()
            preserved_pair = (branch.id, ingredient.id)

            seed_database(session)
            session.commit()

            branch_count = session.scalar(
                select(func.count()).select_from(Branch)
            )
            ingredient_count = session.scalar(
                select(func.count()).select_from(Ingredient)
            )
            expected_pairs = branch_count * ingredient_count
            first_run = session.scalars(
                select(BranchIngredient).order_by(
                    BranchIngredient.branch_id,
                    BranchIngredient.ingredient_id,
                )
            ).all()
            first_values = {
                (link.branch_id, link.ingredient_id): link.is_available
                for link in first_run
            }

            assert len(first_run) == expected_pairs
            assert first_values[preserved_pair] is False
            assert all(
                is_available is True
                for pair, is_available in first_values.items()
                if pair != preserved_pair
            )

            seed_database(session)
            session.commit()

            second_run = session.scalars(
                select(BranchIngredient).order_by(
                    BranchIngredient.branch_id,
                    BranchIngredient.ingredient_id,
                )
            ).all()
            second_values = {
                (link.branch_id, link.ingredient_id): link.is_available
                for link in second_run
            }
            assert len(second_run) == expected_pairs
            assert second_values == first_values
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
