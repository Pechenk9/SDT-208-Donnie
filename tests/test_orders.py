import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SQLAlchemySession, sessionmaker
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
    Order,
    OrderItem,
    OrderItemIngredient,
    Product,
    ProductIngredient,
    User,
    UserRole,
)


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as session:
        group = IngredientGroup(name="Toppings", max_selections=3)
        branch = Branch(
            code="TEST",
            name="Test Branch",
            city="Kyiv",
            address="Test address",
        )
        ingredient_a = Ingredient(
            name="Ingredient A",
            group=group,
            extra_price=Decimal("0.06"),
        )
        ingredient_b = Ingredient(
            name="Ingredient B",
            group=group,
            extra_price=Decimal("0.10"),
        )
        fixed_ingredient = Ingredient(
            name="Fixed Ingredient",
            group=group,
            extra_price=Decimal("0.50"),
        )
        product = Product(
            name="Test Donut",
            base_price=Decimal("3.00"),
            is_active=True,
        )
        product.recipe = [
            ProductIngredient(
                ingredient=ingredient_a,
                default_quantity=Decimal("10"),
                max_quantity=Decimal("30"),
                is_changeable=True,
                unit="g",
            ),
            ProductIngredient(
                ingredient=ingredient_b,
                default_quantity=Decimal("5"),
                max_quantity=Decimal("20"),
                is_changeable=True,
                unit="g",
            ),
            ProductIngredient(
                ingredient=fixed_ingredient,
                default_quantity=Decimal("2"),
                max_quantity=Decimal("2"),
                is_changeable=False,
                unit="g",
            ),
        ]
        session.add_all(
            [
                branch,
                product,
                BranchProduct(
                    branch=branch,
                    product=product,
                    is_available=True,
                ),
                BranchIngredient(
                    branch=branch,
                    ingredient=ingredient_a,
                    is_available=True,
                ),
                BranchIngredient(
                    branch=branch,
                    ingredient=ingredient_b,
                    is_available=True,
                ),
                BranchIngredient(
                    branch=branch,
                    ingredient=fixed_ingredient,
                    is_available=True,
                ),
            ]
        )
        session.commit()
        ids = {
            "branch": branch.id,
            "product": product.id,
            "ingredient_a": ingredient_a.id,
            "ingredient_b": ingredient_b.id,
            "fixed_ingredient": fixed_ingredient.id,
        }

    def override_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield test_sessions, ids
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(database):
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def submit(client, ids, items):
    return client.post(
        "/orders",
        data={
            "customer_name": "Test Customer",
            "customer_phone": "0671234567",
            "branch_id": str(ids["branch"]),
            "fulfillment_type": "pickup",
            "items_json": json.dumps(items),
        },
    )


def order_rows(database):
    test_sessions, _ = database
    with test_sessions() as session:
        order = session.scalar(select(Order))
        order_items = session.scalars(
            select(OrderItem).order_by(OrderItem.id)
        ).all()
        ingredients = session.scalars(
            select(OrderItemIngredient).order_by(OrderItemIngredient.id)
        ).all()
        return order, order_items, ingredients


def test_creates_order_for_one_product_and_persists_customizations(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 25},
                    {"ingredient_id": ids["ingredient_b"], "quantity": 10},
                    {"ingredient_id": ids["fixed_ingredient"], "quantity": 2},
                ],
            }
        ],
    )

    assert response.status_code == 303
    order, items, ingredients = order_rows(database)
    assert response.headers["location"] == f"/orders/{order.id}/receipt"
    assert order.total_price == Decimal("18.96")
    assert len(items) == 1
    assert items[0].unit_price == Decimal("3.16")
    assert {
        ingredient.ingredient_id: ingredient.quantity
        for ingredient in ingredients
    } == {
        ids["ingredient_a"]: Decimal("25.000"),
        ids["ingredient_b"]: Decimal("10.000"),
        ids["fixed_ingredient"]: Decimal("2.000"),
    }


def test_same_product_cart_lines_keep_separate_customizations(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 3,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 15}
                ],
            },
            {
                "product_id": ids["product"],
                "quantity": 3,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 0}
                ],
            },
        ],
    )

    assert response.status_code == 303
    order, items, ingredients = order_rows(database)
    assert order.total_price == Decimal("18.18")
    assert len(items) == 2
    assert [item.unit_price for item in items] == [
        Decimal("3.06"),
        Decimal("3.00"),
    ]
    assert len(ingredients) == 1
    assert ingredients[0].order_item_id == items[0].id
    assert ingredients[0].quantity == Decimal("15.000")


def test_default_reduced_and_removed_ingredients_do_not_change_price(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 3,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10},
                    {"ingredient_id": ids["ingredient_b"], "quantity": 3},
                ],
            },
            {
                "product_id": ids["product"],
                "quantity": 3,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 0}
                ],
            },
        ],
    )

    assert response.status_code == 303
    order, items, ingredients = order_rows(database)
    assert order.total_price == Decimal("18.00")
    assert [item.unit_price for item in items] == [
        Decimal("3.00"),
        Decimal("3.00"),
    ]
    assert len(ingredients) == 2


def test_rejects_empty_or_malformed_cart_lines(client, database):
    _, ids = database
    invalid_carts = [
        [],
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
            }
        ],
        ["not a cart line"],
    ]
    for items in invalid_carts:
        response = submit(client, ids, items)
        assert response.status_code == 400
    assert order_rows(database)[0] is None


def test_rejects_duplicate_or_unrelated_ingredient_ids(client, database):
    _, ids = database
    duplicate = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10},
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10},
                ],
            }
        ],
    )
    unrelated = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": 9999, "quantity": 10},
                ],
            }
        ],
    )
    assert duplicate.status_code == 400
    assert unrelated.status_code == 400
    assert order_rows(database)[0] is None
    assert order_rows(database)[0] is None


def test_rejects_quantity_above_recipe_maximum(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 31}
                ],
            }
        ],
    )
    assert response.status_code == 400
    assert order_rows(database)[0] is None


def test_rejects_unavailable_product_and_ingredient(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        availability = session.get(BranchProduct, (ids["branch"], ids["product"]))
        availability.is_available = False
        session.commit()

    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [],
            }
        ],
    )
    assert response.status_code == 400

    with test_sessions() as session:
        availability = session.get(BranchProduct, (ids["branch"], ids["product"]))
        availability.is_available = True
        ingredient_availability = session.get(
            BranchIngredient,
            (ids["branch"], ids["ingredient_a"]),
        )
        ingredient_availability.is_available = False
        session.commit()

    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10}
                ],
            }
        ],
    )
    assert response.status_code == 400
    assert order_rows(database)[0] is None


def test_rejects_inactive_ingredient_with_positive_quantity(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        ingredient = session.get(Ingredient, ids["ingredient_a"])
        ingredient.is_active = False
        session.commit()

    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10}
                ],
            }
        ],
    )
    assert response.status_code == 400
    assert order_rows(database)[0] is None


def test_zero_quantity_does_not_require_ingredient_availability(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        ingredient = session.get(Ingredient, ids["ingredient_a"])
        ingredient.is_active = False
        availability = session.get(
            BranchIngredient,
            (ids["branch"], ids["ingredient_a"]),
        )
        availability.is_available = False
        session.commit()

    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 0}
                ],
            }
        ],
    )
    assert response.status_code == 303
    order, items, ingredients = order_rows(database)
    assert order.total_price == Decimal("18.00")
    assert len(items) == 1
    assert ingredients == []


def test_missing_branch_ingredient_record_means_no_restriction(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        availability = session.get(
            BranchIngredient,
            (ids["branch"], ids["ingredient_a"]),
        )
        session.delete(availability)
        session.commit()

    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 6,
                "ingredients": [
                    {"ingredient_id": ids["ingredient_a"], "quantity": 10}
                ],
            }
        ],
    )
    assert response.status_code == 303
    assert len(order_rows(database)[2]) == 1


def test_rejects_orders_below_six_donuts(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        [
            {
                "product_id": ids["product"],
                "quantity": 5,
                "ingredients": [],
            }
        ],
    )
    assert response.status_code == 400
    assert order_rows(database)[0] is None


def test_rolls_back_order_when_saving_fails(client, database):
    _, ids = database

    def fail_before_flush(session, flush_context, instances):
        if any(isinstance(instance, Order) for instance in session.new):
            raise SQLAlchemyError("internal database detail")

    event.listen(SQLAlchemySession, "before_flush", fail_before_flush)
    try:
        response = submit(
            client,
            ids,
            [
                {
                    "product_id": ids["product"],
                    "quantity": 6,
                    "ingredients": [],
                }
            ],
        )
    finally:
        event.remove(SQLAlchemySession, "before_flush", fail_before_flush)

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not create order"
    _, items, ingredients = order_rows(database)
    assert items == []
    assert ingredients == []


def test_associates_order_with_optional_authenticated_customer(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        user = User(
            first_name="Test",
            last_name="Customer",
            email="customer@example.com",
            password_hash="test-hash",
            role=UserRole.CUSTOMER,
        )
        session.add(user)
        session.commit()
        user_id = user.id

    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        first_name="Test",
        last_name="Customer",
        email="customer@example.com",
        password_hash="test-hash",
        role=UserRole.CUSTOMER,
    )
    try:
        response = submit(
            client,
            ids,
            [
                {
                    "product_id": ids["product"],
                    "quantity": 6,
                    "ingredients": [],
                }
            ],
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 303
    order, _, _ = order_rows(database)
    assert order.user_id == user_id
