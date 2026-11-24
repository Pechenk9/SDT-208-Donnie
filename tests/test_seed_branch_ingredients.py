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
from app.seed import seed_catalog, seed_database
from app.seed_data import INGREDIENT_GROUPS


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


def test_seed_catalog_updates_mandatory_flags_without_overwriting_group_data():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            seed_catalog(session)
            session.commit()

            groups = {
                group.name_en: group
                for group in session.scalars(select(IngredientGroup)).all()
            }
            original_data = {
                name_en: (
                    group.id,
                    group.name,
                    group.name_en,
                    group.max_selections,
                )
                for name_en, group in groups.items()
            }
            for group in groups.values():
                group.is_mandatory = not group.is_mandatory
                group.max_selections += 1
            session.commit()
            updated_max_selections = {
                name_en: group.max_selections
                for name_en, group in groups.items()
            }

            seed_catalog(session)
            session.commit()

            groups_after_seed = session.scalars(
                select(IngredientGroup)
            ).all()
            assert len(groups_after_seed) == len(INGREDIENT_GROUPS)

            expected_mandatory = {
                data["name_en"]: data["is_mandatory"]
                for data in INGREDIENT_GROUPS
            }
            for group in groups_after_seed:
                assert group.is_mandatory is expected_mandatory[group.name_en]
                assert (group.id, group.name, group.name_en) == original_data[
                    group.name_en
                ][:3]
                assert group.max_selections == updated_max_selections[
                    group.name_en
                ]
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
