import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Base, get_session
from app.main import app
from app.models import (
    Branch,
    BranchProduct,
    Ingredient,
    IngredientGroup,
    Order,
    OrderItem,
    OrderStatus,
    FulfillmentType,
    Product,
    ProductIngredient,
)
from app.order_extras import KYIV_TZ, available_slots, schedule_options
from app.product_info import allergens_for, bestseller_ids


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
        dough = Ingredient(name="Classic dough", group=group)
        nuts = Ingredient(name="Crushed pistachios", group=group)
        branch = Branch(code="TEST", name="Test Branch", city="Kyiv", address="Street 1")
        products = [
            Product(name=f"Donut {index}", base_price=Decimal("3.00"), is_active=True)
            for index in range(4)
        ]
        products[0].recipe = [
            ProductIngredient(
                ingredient=dough,
                default_quantity=Decimal("70"),
                max_quantity=Decimal("70"),
                is_changeable=False,
                unit="g",
            ),
            ProductIngredient(
                ingredient=nuts,
                default_quantity=Decimal("0"),
                max_quantity=Decimal("10"),
                is_changeable=True,
                unit="g",
            ),
        ]
        products[1].recipe = [
            ProductIngredient(
                ingredient=dough,
                default_quantity=Decimal("70"),
                max_quantity=Decimal("70"),
                is_changeable=False,
                unit="g",
            ),
        ]
        session.add_all([branch, *products])
        session.add_all(
            BranchProduct(branch=branch, product=product, is_available=True)
            for product in products
        )
        session.commit()
        ids = {
            "branch": branch.id,
            "products": [product.id for product in products],
            "dough": dough.id,
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


def submit(client, ids, **extra):
    data = {
        "customer_name": "Test Customer",
        "customer_phone": "0671234567",
        "branch_id": str(ids["branch"]),
        "fulfillment_type": "pickup",
        "items_json": json.dumps(
            [
                {
                    "product_id": ids["products"][1],
                    "quantity": 6,
                    "ingredients": [{"ingredient_id": ids["dough"], "quantity": 70}],
                }
            ]
        ),
    }
    data.update({key: str(value) for key, value in extra.items()})
    return client.post("/orders", data=data)


def saved_order(database):
    test_sessions, _ = database
    with test_sessions() as session:
        return session.scalar(select(Order))


# ---------- celebration add-ons ----------


def test_gift_box_candles_and_postcard_are_priced_on_the_server(client, database):
    _, ids = database
    response = submit(
        client,
        ids,
        gift_box="true",
        candles=5,
        postcard_message="  Happy birthday, Sofia!  ",
        tip_percent=10,
    )

    assert response.status_code == 303
    order = saved_order(database)
    # 6 × $3.00 donuts + $2.00 box + 5 × $0.20 candles
    assert order.extras_amount == Decimal("3.00")
    assert order.total_price == Decimal("21.00")
    assert order.donuts_amount == Decimal("18.00")
    # The tip is a share of the donuts only.
    assert order.tip_amount == Decimal("1.80")
    assert order.gift_box is True
    assert order.candles == 5
    assert order.postcard_message == "Happy birthday, Sofia!"


def test_order_without_extras_keeps_old_totals(client, database):
    _, ids = database
    assert submit(client, ids).status_code == 303
    order = saved_order(database)
    assert order.total_price == Decimal("18.00")
    assert order.extras_amount == Decimal("0.00")
    assert not order.has_extras
    assert order.scheduled_date is None and order.time_slot is None


@pytest.mark.parametrize("candles", [-1, 25])
def test_rejects_invalid_candle_count(client, database, candles):
    _, ids = database
    response = submit(client, ids, candles=candles)
    assert response.status_code == 400
    assert saved_order(database) is None


def test_rejects_too_long_postcard(client, database):
    _, ids = database
    response = submit(client, ids, postcard_message="x" * 201)
    assert response.status_code == 400
    assert response.json()["detail"] == "Postcard message is too long"


def test_receipt_shows_extras_and_schedule(client, database):
    _, ids = database
    tomorrow = (datetime.now(KYIV_TZ) + timedelta(days=1)).date()
    submit(
        client,
        ids,
        gift_box="true",
        postcard_message="For you",
        scheduled_date=tomorrow.isoformat(),
        time_slot="12:00-15:00",
    )
    order = saved_order(database)
    page = client.get(f"/orders/{order.id}/receipt")
    assert page.status_code == 200
    assert "Extras: gift box, postcard" in page.text
    assert "12:00 – 15:00" in page.text
    assert "For you" in page.text


# ---------- pre-order time slots ----------


def test_pre_order_for_tomorrow_is_saved(client, database):
    _, ids = database
    tomorrow = (datetime.now(KYIV_TZ) + timedelta(days=1)).date()
    response = submit(
        client,
        ids,
        scheduled_date=tomorrow.isoformat(),
        time_slot="09:30-12:00",
    )
    assert response.status_code == 303
    order = saved_order(database)
    assert order.scheduled_date == tomorrow
    assert order.time_slot == "09:30-12:00"


@pytest.mark.parametrize(
    "days, slot, detail",
    [
        (1, "08:00-09:00", "Invalid time window"),
        (-1, "12:00-15:00", "This time window is no longer available"),
        (8, "12:00-15:00", "This time window is no longer available"),
    ],
)
def test_rejects_bad_pre_orders(client, database, days, slot, detail):
    _, ids = database
    day = (datetime.now(KYIV_TZ) + timedelta(days=days)).date()
    response = submit(client, ids, scheduled_date=day.isoformat(), time_slot=slot)
    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_rejects_half_filled_schedule(client, database):
    _, ids = database
    response = submit(client, ids, time_slot="12:00-15:00")
    assert response.status_code == 400
    assert response.json()["detail"] == "Choose both a day and a time window"


def test_table_orders_cannot_be_scheduled(client, database):
    _, ids = database
    tomorrow = (datetime.now(KYIV_TZ) + timedelta(days=1)).date()
    response = submit(
        client,
        ids,
        table_number=3,
        scheduled_date=tomorrow.isoformat(),
        time_slot="12:00-15:00",
    )
    assert response.status_code == 400


def test_today_only_offers_windows_starting_an_hour_later():
    now = datetime(2026, 11, 22, 11, 30, tzinfo=KYIV_TZ)
    assert available_slots(now.date(), now) == [
        "15:00-18:00",
        "18:00-21:00",
    ]
    late = datetime(2026, 11, 22, 20, 0, tzinfo=KYIV_TZ)
    options = schedule_options(late)
    # Nothing left today, so the picker starts tomorrow and covers a week.
    assert options[0]["date"] == "2026-11-23"
    assert len(options) == 7


# ---------- product info ----------


def test_allergens_follow_ingredient_names():
    assert allergens_for(["Classic dough", "Crushed pistachios"]) == [
        "Gluten",
        "Eggs",
        "Milk",
        "Tree nuts",
    ]
    assert allergens_for(["Neon sprinkles", "Blueberry jam"]) == []


def test_product_page_lists_allergens_of_the_default_recipe(client, database):
    _, ids = database
    page = client.get(f"/product/{ids['products'][0]}")
    assert page.status_code == 200
    # Pistachios are not in the default recipe (0 g), so no tree nuts.
    assert "<li>Gluten</li>" in page.text
    assert "<li>Tree nuts</li>" not in page.text
    assert "Freshness and storage" in page.text
    assert "You may also like" in page.text


def test_bestsellers_are_the_most_ordered_donuts(database):
    test_sessions, ids = database
    first, second, third, fourth = ids["products"]
    with test_sessions() as session:
        def order(status, *lines):
            session.add(
                Order(
                    branch_id=ids["branch"],
                    status=status,
                    fulfillment_type=FulfillmentType.PICKUP,
                    customer_name="A",
                    customer_phone="0671234567",
                    total_price=Decimal("0"),
                    items=[
                        OrderItem(
                            product_id=product_id,
                            name_snapshot="x",
                            quantity=quantity,
                            unit_price=Decimal("1"),
                        )
                        for product_id, quantity in lines
                    ],
                )
            )

        order(OrderStatus.COMPLETED, (first, 10), (second, 6))
        order(OrderStatus.PENDING, (third, 7))
        # Cancelled orders don't count.
        order(OrderStatus.CANCELLED, (fourth, 50))
        session.commit()

        assert bestseller_ids(session) == {first, second, third}
        assert bestseller_ids(session, limit=1) == {first}


def test_store_marks_bestsellers(client, database):
    test_sessions, ids = database
    with test_sessions() as session:
        session.add(
            Order(
                branch_id=ids["branch"],
                fulfillment_type=FulfillmentType.PICKUP,
                customer_name="A",
                customer_phone="0671234567",
                total_price=Decimal("0"),
                items=[
                    OrderItem(
                        product_id=ids["products"][2],
                        name_snapshot="x",
                        quantity=6,
                        unit_price=Decimal("1"),
                    )
                ],
            )
        )
        session.commit()

    page = client.get("/store")
    data = json.loads(
        page.text.split('<script id="store-data" type="application/json">')[1].split("</script>")[0]
    )
    flags = {product["id"]: product["is_bestseller"] for product in data["products"]}
    assert flags[ids["products"][2]] is True
    assert flags[ids["products"][0]] is False


# ---------- order tracker on the receipt ----------


@pytest.mark.parametrize(
    "status, fulfillment, table, current, complete, labels",
    [
        (OrderStatus.PENDING, FulfillmentType.PICKUP, None, 0, False, ("Ready", "Picked up")),
        (OrderStatus.PREPARING, FulfillmentType.PICKUP, None, 1, False, ("Ready", "Picked up")),
        (OrderStatus.READY, FulfillmentType.DELIVERY, None, 2, False, ("On the way", "Delivered")),
        (OrderStatus.COMPLETED, FulfillmentType.PICKUP, 4, 3, True, ("Ready", "Served")),
    ],
)
def test_order_progress_follows_status(status, fulfillment, table, current, complete, labels):
    from app.order_extras import order_progress

    order = Order(
        status=status,
        fulfillment_type=fulfillment,
        table_number=table,
        branch=Branch(code="X", name="Donnie Kyiv", city="Kyiv", address="A"),
    )
    progress = order_progress(order)
    assert progress["current"] == current
    assert progress["complete"] is complete
    assert progress["steps"] == ["Placed", "Baking", *labels]
    assert progress["hint"]


def test_cancelled_order_has_no_tracker(client, database):
    test_sessions, ids = database
    submit(client, ids)
    with test_sessions() as session:
        order = session.scalar(select(Order))
        order.status = OrderStatus.CANCELLED
        session.commit()
        order_id = order.id

    page = client.get(f"/orders/{order_id}/receipt")
    assert 'id="order-track"' not in page.text
    assert "This order was cancelled." in page.text


def test_receipt_shows_tracker_for_new_order(client, database):
    _, ids = database
    submit(client, ids)
    order = saved_order(database)
    page = client.get(f"/orders/{order.id}/receipt")
    assert 'id="order-track"' in page.text
    assert 'data-current="0"' in page.text
    assert "Placed: in progress" in page.text
