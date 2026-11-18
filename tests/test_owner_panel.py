from decimal import Decimal

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Base, get_session
from app.deps import get_current_user
from app.main import app
from app.models import (
    Branch,
    BranchIngredient,
    BranchProduct,
    Ingredient,
    IngredientGroup,
    Product,
    ProductIngredient,
    User,
    UserRole,
)


@pytest.fixture
def owner_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as session:
        branch_a = Branch(
            code="OWNER-A",
            name="Owner Branch A",
            city="Kyiv",
            address="A address",
        )
        branch_b = Branch(
            code="OWNER-B",
            name="Owner Branch B",
            city="Lviv",
            address="B address",
        )
        group = IngredientGroup(name="Owner Group", max_selections=3)
        other_group = IngredientGroup(name="Other Owner Group", max_selections=2)
        ingredient = Ingredient(
            name="Existing Ingredient",
            description="Ingredient description",
            group=group,
            extra_price=Decimal("0.25"),
            is_active=True,
        )
        product = Product(
            name="Existing Product",
            description="Product description",
            base_price=Decimal("3.50"),
            calories=250,
            image_url="/static/images/donut.png",
            is_active=True,
        )
        product.recipe = [
            ProductIngredient(
                ingredient=ingredient,
                default_quantity=Decimal("5"),
                max_quantity=Decimal("10"),
                unit="g",
                is_changeable=True,
            )
        ]
        owner = User(
            first_name="Network",
            last_name="Owner",
            email="network-owner@example.com",
            password_hash="test-hash",
            role=UserRole.OWNER,
        )
        manager = User(
            first_name="Branch",
            last_name="Manager",
            email="branch-manager@example.com",
            password_hash="test-hash",
            role=UserRole.MANAGER,
            managed_branches=[branch_a],
        )
        customer = User(
            first_name="Available",
            last_name="Customer",
            email="available-customer@example.com",
            password_hash="test-hash",
            role=UserRole.CUSTOMER,
        )
        session.add_all(
            [
                branch_a,
                branch_b,
                group,
                other_group,
                ingredient,
                product,
                owner,
                manager,
                customer,
                BranchProduct(
                    branch=branch_a,
                    product=product,
                    is_available=False,
                    price=Decimal("4.25"),
                ),
                BranchProduct(
                    branch=branch_b,
                    product=product,
                    is_available=True,
                    price=Decimal("4.75"),
                ),
                BranchIngredient(
                    branch=branch_a,
                    ingredient=ingredient,
                    is_available=False,
                ),
                BranchIngredient(
                    branch=branch_b,
                    ingredient=ingredient,
                    is_available=True,
                ),
            ]
        )
        session.commit()
        ids = {
            "branch_a": branch_a.id,
            "branch_b": branch_b.id,
            "group": group.id,
            "other_group": other_group.id,
            "ingredient": ingredient.id,
            "product": product.id,
            "owner": owner.id,
            "manager": manager.id,
            "customer": customer.id,
        }

    def override_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, follow_redirects=False) as client:
            yield client, test_sessions, ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def authenticate(user_id):
    def provide_user(
        request: Request,
        session: Session = Depends(get_session),
    ):
        user = session.get(User, user_id)
        request.state.current_user = user
        return user

    app.dependency_overrides[get_current_user] = provide_user


def test_owner_can_view_all_panel_sections(owner_context):
    client, _, ids = owner_context
    authenticate(ids["owner"])

    response = client.get("/owner")

    assert response.status_code == 200
    assert "Overview" in response.text
    assert "Staff Management" in response.text
    assert "Products" in response.text
    assert "Ingredients" in response.text
    assert "Owner Branch A" in response.text
    assert "Existing Product" in response.text
    assert "Existing Ingredient" in response.text


@pytest.mark.parametrize("role", ["customer", "manager"])
def test_non_owners_cannot_access_owner_panel_or_operations(owner_context, role):
    client, _, ids = owner_context
    authenticate(ids[role])
    form_data = {
        "branch_id": ids["branch_a"],
        "user_id": ids["customer"],
        "name": "Forged Product",
        "base_price": "1.00",
        "extra_price": "0.10",
        "group_id": ids["group"],
    }

    responses = [
        client.get("/owner"),
        client.post("/owner/staff/assign", data=form_data),
        client.post("/owner/staff/remove", data=form_data),
        client.post("/owner/products/create", data=form_data),
        client.post(
            f"/owner/products/{ids['product']}/edit",
            data=form_data,
        ),
        client.post("/owner/ingredients/create", data=form_data),
        client.post(
            f"/owner/ingredients/{ids['ingredient']}/edit",
            data=form_data,
        ),
    ]

    assert all(response.status_code == 403 for response in responses)


def test_unauthenticated_owner_posts_are_rejected(owner_context):
    client, _, _ = owner_context

    response = client.post(
        "/owner/products/create",
        data={"name": "Unauthenticated", "base_price": "1.00"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_manager_assignments_update_role_and_preserve_other_branches(owner_context):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    assign_a = client.post(
        "/owner/staff/assign",
        data={"branch_id": ids["branch_a"], "user_id": ids["customer"]},
    )
    assign_b = client.post(
        "/owner/staff/assign",
        data={"branch_id": ids["branch_b"], "user_id": ids["customer"]},
    )
    assert assign_a.status_code == 303
    assert assign_b.status_code == 303

    remove_a = client.post(
        "/owner/staff/remove",
        data={"branch_id": ids["branch_a"], "user_id": ids["customer"]},
    )
    assert remove_a.status_code == 303
    with test_sessions() as session:
        customer = session.get(User, ids["customer"])
        assert customer.role == UserRole.MANAGER
        assert [branch.id for branch in customer.managed_branches] == [
            ids["branch_b"]
        ]

    remove_b = client.post(
        "/owner/staff/remove",
        data={"branch_id": ids["branch_b"], "user_id": ids["customer"]},
    )
    assert remove_b.status_code == 303
    with test_sessions() as session:
        customer = session.get(User, ids["customer"])
        assert customer is not None
        assert customer.role == UserRole.CUSTOMER
        assert customer.managed_branches == []


def test_manager_assignment_rejects_owner_and_duplicate_links(owner_context):
    client, _, ids = owner_context
    authenticate(ids["owner"])

    duplicate = client.post(
        "/owner/staff/assign",
        data={"branch_id": ids["branch_a"], "user_id": ids["manager"]},
    )
    owner_assignment = client.post(
        "/owner/staff/assign",
        data={"branch_id": ids["branch_a"], "user_id": ids["owner"]},
    )
    invalid_branch = client.post(
        "/owner/staff/assign",
        data={"branch_id": 99999, "user_id": ids["customer"]},
    )

    assert duplicate.status_code == 303
    assert "already-assigned" in duplicate.headers["location"]
    assert owner_assignment.status_code == 303
    assert invalid_branch.status_code == 303


def test_owner_creates_global_product_without_branch_links(owner_context):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    response = client.post(
        "/owner/products/create",
        data={
            "name": "New Global Product",
            "description": "A network-wide product",
            "base_price": "6.25",
            "calories": "310",
            "image_url": "/static/images/new.png",
            "is_active": "true",
        },
    )

    assert response.status_code == 303
    assert "product-created" in response.headers["location"]
    with test_sessions() as session:
        product = session.query(Product).filter_by(name="New Global Product").one()
        assert product.base_price == Decimal("6.25")
        assert product.calories == 310
        assert product.is_active is True
        assert product.branch_availability == []


def test_owner_edits_product_without_changing_branch_associations(owner_context):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    response = client.post(
        f"/owner/products/{ids['product']}/edit",
        data={
            "name": "Edited Global Product",
            "description": "Updated description",
            "base_price": "5.00",
            "calories": "280",
            "image_url": "/static/images/edited.png",
            "is_active": "false",
        },
    )

    assert response.status_code == 303
    with test_sessions() as session:
        product = session.get(Product, ids["product"])
        assert product.name == "Edited Global Product"
        assert product.base_price == Decimal("5.00")
        assert product.is_active is False
        association_a = session.get(
            BranchProduct,
            (ids["branch_a"], ids["product"]),
        )
        association_b = session.get(
            BranchProduct,
            (ids["branch_b"], ids["product"]),
        )
        assert association_a.is_available is False
        assert association_a.price == Decimal("4.25")
        assert association_b.is_available is True
        assert association_b.price == Decimal("4.75")


def test_owner_creates_global_ingredient_without_branch_links(owner_context):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    response = client.post(
        "/owner/ingredients/create",
        data={
            "name": "New Global Ingredient",
            "description": "A network-wide ingredient",
            "extra_price": "0.35",
            "group_id": ids["other_group"],
            "is_active": "true",
        },
    )

    assert response.status_code == 303
    with test_sessions() as session:
        ingredient = (
            session.query(Ingredient)
            .filter_by(name="New Global Ingredient")
            .one()
        )
        assert ingredient.extra_price == Decimal("0.35")
        assert ingredient.group_id == ids["other_group"]
        assert ingredient.branch_availability == []
        assert ingredient.product_recipes == []


def test_owner_edits_ingredient_without_changing_recipe_or_branch_links(
    owner_context,
):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    response = client.post(
        f"/owner/ingredients/{ids['ingredient']}/edit",
        data={
            "name": "Edited Ingredient",
            "description": "Updated ingredient",
            "extra_price": "0.45",
            "group_id": ids["other_group"],
            "is_active": "false",
        },
    )

    assert response.status_code == 303
    with test_sessions() as session:
        ingredient = session.get(Ingredient, ids["ingredient"])
        assert ingredient.name == "Edited Ingredient"
        assert ingredient.extra_price == Decimal("0.45")
        assert ingredient.group_id == ids["other_group"]
        assert ingredient.is_active is False
        assert len(ingredient.product_recipes) == 1
        assert ingredient.product_recipes[0].default_quantity == Decimal("5")
        association_a = session.get(
            BranchIngredient,
            (ids["branch_a"], ids["ingredient"]),
        )
        association_b = session.get(
            BranchIngredient,
            (ids["branch_b"], ids["ingredient"]),
        )
        assert association_a.is_available is False
        assert association_b.is_available is True


def test_invalid_catalogue_forms_do_not_create_records(owner_context):
    client, test_sessions, ids = owner_context
    authenticate(ids["owner"])

    duplicate_product = client.post(
        "/owner/products/create",
        data={"name": "Existing Product", "base_price": "3.50"},
    )
    duplicate_ingredient = client.post(
        "/owner/ingredients/create",
        data={
            "name": "Existing Ingredient",
            "extra_price": "0.25",
            "group_id": ids["group"],
        },
    )
    invalid_product = client.post(
        "/owner/products/create",
        data={"name": "Bad Price", "base_price": "-1.00"},
    )
    missing_group = client.post(
        "/owner/ingredients/create",
        data={
            "name": "Bad Group",
            "extra_price": "0.10",
            "group_id": "99999",
        },
    )

    assert "duplicate" in duplicate_product.headers["location"]
    assert "duplicate" in duplicate_ingredient.headers["location"]
    assert "invalid-form" in invalid_product.headers["location"]
    assert "group-not-found" in missing_group.headers["location"]
    with test_sessions() as session:
        assert session.query(Product).filter_by(name="Bad Price").first() is None
        assert session.query(Ingredient).filter_by(name="Bad Group").first() is None
