import json
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    BranchIngredient,
    Ingredient,
    Order,
    OrderItem,
    OrderItemIngredient,
)

from test_orders import client, database  # noqa: F401


def _select_branch(client, database):
    _, ids = database
    client.cookies.set("selected_branch", "TEST")
    return ids


def test_custom_donut_page_is_localized_and_linked(client, database):
    ids = _select_branch(client, database)
    english = client.get("/en/custom-donut")
    ukrainian = client.get("/ua/custom-donut")

    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert 'src="/static/js/custom_donut.js?' in english.text
    assert client.get("/static/js/custom_donut.js").status_code == 200
    assert client.get("/static/css/custom-donut.css").status_code == 200
    assert f'href="/ua/custom-donut"' in english.text
    assert "Build your custom donut" in english.text
    assert ukrainian.status_code == 200
    assert '<html lang="uk">' in ukrainian.text
    assert "Створіть власний пончик" in ukrainian.text
    assert "/ua/custom-donut" in ukrainian.text
    legacy = client.get("/custom-donut")
    assert legacy.status_code == 307
    assert legacy.headers["location"] == "/ua/custom-donut"
    assert ids["branch"]


def test_custom_donut_data_requires_a_selected_branch(client, database):
    response = client.get("/en/api/custom-donut/ingredients")
    assert response.status_code == 409
    assert response.json()["detail"] == "Choose a branch first"


def test_custom_donut_api_enforces_mandatory_max_and_availability(client, database):
    test_sessions, ids = database
    client.cookies.set("selected_branch", "TEST")
    with test_sessions() as session:
        group = session.get(Ingredient, ids["ingredient_a"]).group
        group.is_mandatory = True
        group.max_selections = 2
        unavailable = session.get(BranchIngredient, (ids["branch"], ids["ingredient_b"]))
        unavailable.is_available = False
        extra = Ingredient(name="Extra Ingredient", group=group)
        session.add(extra)
        session.flush()
        session.add(
            BranchIngredient(
                branch_id=ids["branch"],
                ingredient_id=extra.id,
                is_available=True,
            )
        )
        extra_id = extra.id
        session.commit()

    catalog = client.get("/en/api/custom-donut/ingredients")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["price"] == "150.00"
    assert payload["groups"][0]["is_mandatory"] is True
    assert next(
        entry for entry in payload["groups"][0]["ingredients"]
        if entry["id"] == ids["ingredient_b"]
    )["is_available"] is False

    valid = client.post(
        "/en/api/custom-donut/validate",
        json={"ingredient_ids": [ids["ingredient_a"]]},
    )
    assert valid.status_code == 200
    assert valid.json() == {
        "price": "150.00",
        "ingredients": [{"ingredient_id": ids["ingredient_a"], "quantity": 1}],
    }

    assert client.post(
        "/en/api/custom-donut/validate",
        json={"ingredient_ids": []},
    ).status_code == 400
    assert client.post(
        "/en/api/custom-donut/validate",
        json={"ingredient_ids": [ids["ingredient_a"], ids["fixed_ingredient"], extra_id]},
    ).status_code == 400
    unavailable_response = client.post(
        "/en/api/custom-donut/validate",
        json={"ingredient_ids": [ids["ingredient_b"]]},
    )
    assert unavailable_response.status_code == 400
    assert "unavailable at this branch" in unavailable_response.json()["detail"]


def test_custom_donut_order_persists_choices_at_fixed_server_price(client, database):
    test_sessions, ids = database
    client.cookies.set("selected_branch", "TEST")
    with test_sessions() as session:
        group = session.get(Ingredient, ids["ingredient_a"]).group
        group.is_mandatory = True
        session.commit()

    response = client.post(
        "/orders",
        data={
            "customer_name": "Test Customer",
            "customer_phone": "0671234567",
            "branch_id": str(ids["branch"]),
            "fulfillment_type": "pickup",
            "items_json": json.dumps(
                [
                    {
                        "custom_donut": True,
                        "unit_price": 0,
                        "quantity": 6,
                        "ingredients": [
                            {
                                "ingredient_id": ids["ingredient_a"],
                                "quantity": 1,
                            }
                        ],
                    }
                ]
            ),
        },
    )
    assert response.status_code == 303

    with test_sessions() as session:
        order = session.scalar(select(Order))
        order_item = session.scalar(select(OrderItem))
        saved_ingredient = session.scalar(select(OrderItemIngredient))
        assert order.total_price == Decimal("900.00")
        assert order_item.product_id is None
        assert order_item.name_snapshot == "Custom donut"
        assert order_item.unit_price == Decimal("150.00")
        assert saved_ingredient.ingredient_id == ids["ingredient_a"]
        assert saved_ingredient.quantity == Decimal("1.000")


def test_custom_donut_can_be_ordered_with_catalog_donuts(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        group = session.get(Ingredient, ids["ingredient_a"]).group
        group.is_mandatory = True
        session.commit()

    response = client.post(
        "/orders",
        data={
            "customer_name": "Test Customer",
            "customer_phone": "0671234567",
            "branch_id": str(ids["branch"]),
            "fulfillment_type": "pickup",
            "items_json": json.dumps(
                [
                    {
                        "custom_donut": True,
                        "quantity": 1,
                        "ingredients": [
                            {"ingredient_id": ids["ingredient_a"], "quantity": 1},
                        ],
                    },
                    {
                        "product_id": ids["product"],
                        "quantity": 5,
                        "ingredients": [
                            {"ingredient_id": ids["ingredient_a"], "quantity": 10},
                            {"ingredient_id": ids["ingredient_b"], "quantity": 5},
                            {"ingredient_id": ids["fixed_ingredient"], "quantity": 2},
                        ],
                    },
                ]
            ),
        },
    )
    assert response.status_code == 303

    with test_sessions() as session:
        order = session.scalar(select(Order))
        order_items = session.scalars(
            select(OrderItem).order_by(OrderItem.id)
        ).all()
        assert order.total_price == Decimal("165.00")
        assert [item.product_id for item in order_items] == [None, ids["product"]]
