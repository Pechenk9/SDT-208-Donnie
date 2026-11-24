"""Tips, table orders, online payment (LiqPay demo), refunds and QR entry links."""
import json
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urljoin

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_session
from app.deps import get_current_user
from app.main import app
from app.models import Branch, Order, PaymentStatus, User, UserRole

# Reuse the order test database (one branch, one 3.00 donut) and client.
from test_orders import client, database  # noqa: F401  (pytest fixtures)


class _DemoPaymentFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current_form = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self.current_form = {
                "action": attributes.get("action"),
                "input_names": set(),
            }
        elif tag == "input" and self.current_form is not None:
            name = attributes.get("name")
            if name:
                self.current_form["input_names"].add(name)

    def handle_endtag(self, tag):
        if tag == "form" and self.current_form is not None:
            self.forms.append(self.current_form)
            self.current_form = None


def place(client, ids, **extra):
    data = {
        "customer_name": "Test Customer",
        "customer_phone": "0671234567",
        "branch_id": str(ids["branch"]),
        "fulfillment_type": "pickup",
        "items_json": json.dumps(
            [{"product_id": ids["product"], "quantity": 6, "ingredients": []}]
        ),
    }
    data.update({key: str(value) for key, value in extra.items()})
    return client.post("/orders", data=data)


SUCCESS_CARD = "4242424242424242"
DECLINED_CARD = "4000000000000002"


def submit_demo_card(client, checkout, order_id, card=SUCCESS_CARD):
    opened = client.post(checkout["url"], data={"data": checkout["data"], "signature": checkout["signature"]})
    assert opened.status_code == 303
    page = client.get(opened.headers["location"])
    assert page.status_code == 200
    parser = _DemoPaymentFormParser()
    parser.feed(page.text)
    form = next(
        (form for form in parser.forms if "card" in form["input_names"]),
        None,
    )
    assert form is not None
    assert form["action"]
    paid = client.post(urljoin(str(page.url), form["action"]), data={"card": card})
    # result_url carries the order's access token (?t=...) back from LiqPay.
    assert f"/orders/{order_id}/payment-return?t=" in paid.headers["location"]
    return paid


def pay_online(client, order_id, card=SUCCESS_CARD, **data):
    """Runs the browser's LiqPay demo flow and returns the return-page redirect."""
    start = client.post(
        f"/orders/{order_id}/pay",
        data={key: str(v) for key, v in data.items()},
        headers={"Accept": "application/json"},
    )
    if start.status_code != 200:
        return start
    paid = submit_demo_card(client, start.json()["checkout"], order_id, card)
    return client.get(paid.headers["location"])


def get_order(database):
    test_sessions, _ = database
    with test_sessions() as session:
        return session.scalar(select(Order))


def test_order_without_extras_keeps_old_behaviour(client, database):
    _, ids = database
    response = place(client, ids)

    order = get_order(database)
    assert response.headers["location"] == f"/en/orders/{order.id}/receipt"
    assert order.tip_amount == Decimal("0.00")
    assert order.payment_method == "on_receipt"
    assert order.payment_status == PaymentStatus.UNPAID
    assert order.table_number is None


def test_tip_is_calculated_on_the_server(client, database):
    _, ids = database
    place(client, ids, tip_percent=10)

    order = get_order(database)
    assert order.total_price == Decimal("18.00")
    assert order.tip_amount == Decimal("1.80")
    assert order.amount_due == Decimal("19.80")


def test_rejects_unknown_tip_and_payment_method(client, database):
    _, ids = database
    assert place(client, ids, tip_percent=7).status_code == 400
    assert place(client, ids, payment_method="crypto").status_code == 400
    assert get_order(database) is None


def test_table_order_is_saved_and_cannot_be_delivered(client, database):
    _, ids = database
    rejected = place(
        client, ids, table_number=4,
        fulfillment_type="delivery", delivery_address="Somewhere 1",
    )
    assert rejected.status_code == 400
    assert place(client, ids, table_number=0).status_code == 400

    place(client, ids, table_number=4)
    assert get_order(database).table_number == 4


def test_online_payment_success_flow(client, database):
    _, ids = database
    response = place(client, ids, payment_method="online", tip_percent=5)
    order = get_order(database)
    assert response.headers["location"] == f"/en/orders/{order.id}/pay"
    assert order.payment_status == PaymentStatus.PENDING

    page = client.get(f"/en/orders/{order.id}/pay")
    assert page.status_code == 200
    assert "₴18.90" in page.text

    paid = pay_online(client, order.id)
    assert paid.headers["location"] == f"/en/orders/{order.id}/receipt?paid=1"
    order = get_order(database)
    assert order.payment_status == PaymentStatus.PAID
    assert order.paid_at is not None

    # A paid order can't be paid again: the payment page sends you to the receipt.
    again = client.get(f"/en/orders/{order.id}/pay")
    assert again.headers["location"] == f"/en/orders/{order.id}/receipt"
    receipt = client.get(f"/en/orders/{order.id}/receipt")
    assert "Paid" in receipt.text


def test_declined_payment_can_be_retried(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    declined = pay_online(client, order.id, card=DECLINED_CARD)
    assert declined.headers["location"] == f"/en/orders/{order.id}/pay?declined=1"
    assert get_order(database).payment_status == PaymentStatus.FAILED

    pay_online(client, order.id)
    assert get_order(database).payment_status == PaymentStatus.PAID


def test_on_receipt_orders_cannot_be_paid_online(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)
    response = client.post(f"/orders/{order.id}/pay")
    assert response.status_code == 400
    assert get_order(database).payment_status == PaymentStatus.UNPAID


def _login_as(database, role, branch_id=None):
    test_sessions, _ = database
    with test_sessions() as session:
        user = User(
            first_name="Staff",
            last_name="Member",
            email=f"{role.value}@example.com",
            password_hash="test-hash",
            role=role,
        )
        if branch_id is not None:
            user.managed_branches.append(session.get(Branch, branch_id))
        session.add(user)
        session.commit()
        user_id = user.id

    def provide_user(request: Request, session: Session = Depends(get_session)):
        user = session.get(User, user_id)
        request.state.current_user = user
        return user

    app.dependency_overrides[get_current_user] = provide_user


def test_manager_refunds_paid_online_order(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    pay_online(client, order.id)

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        dashboard = client.get("/en/manager")
        assert dashboard.status_code == 200
        assert f"#{order.id}" in dashboard.text
        assert "Refund" in dashboard.text

        response = client.post(
            f"/manager/orders/{order.id}/refund",
            data={"branch_id": ids["branch"]},
        )
        assert response.status_code == 303
        order = get_order(database)
        assert order.payment_status == PaymentStatus.REFUNDED
        assert order.refunded_at is not None

        # Refunding twice is rejected.
        again = client.post(
            f"/manager/orders/{order.id}/refund",
            data={"branch_id": ids["branch"]},
        )
        assert again.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_customer_cannot_refund(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    pay_online(client, order.id)

    _login_as(database, UserRole.CUSTOMER)
    try:
        response = client.post(
            f"/manager/orders/{order.id}/refund",
            data={"branch_id": ids["branch"]},
        )
        assert response.status_code == 403
        assert get_order(database).payment_status == PaymentStatus.PAID
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_qr_link_opens_branch_menu(client, database):
    assert client.get("/qr/TEST").headers["location"] == "/en/store?branch=TEST"
    assert client.get("/qr/TEST?table=3").headers["location"] == "/en/table?branch=TEST&table=3"
    assert client.get("/en/table").status_code == 200
    assert client.get("/qr/NOPE").status_code == 404
    assert client.get("/qr/TEST?table=100").status_code == 400


def test_tip_can_be_changed_on_the_payment_screen(client, database):
    _, ids = database
    place(client, ids, payment_method="online", tip_percent=5)
    order = get_order(database)

    pay_online(client, order.id, tip_percent=15)
    order = get_order(database)
    assert order.tip_amount == Decimal("2.70")
    assert order.amount_due == Decimal("20.70")
    assert order.payment_status == PaymentStatus.PAID


def test_rejects_unknown_tip_on_payment_screen(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    response = client.post(f"/orders/{order.id}/pay", data={"tip_percent": 50})
    assert response.status_code == 400
    assert get_order(database).payment_status == PaymentStatus.PENDING
