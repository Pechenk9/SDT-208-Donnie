"""LiqPay: data + signature, the demo checkout, callbacks, refunds and the real API client."""
import base64
import hashlib
import json
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app import liqpay
from app.deps import get_current_user
from app.main import app
from app.models import DemoLiqpayPayment, PaymentStatus, UserRole

from test_orders import client, database  # noqa: F401  (pytest fixtures)
from test_payments import DECLINED_CARD, _login_as, get_order, pay_online, place


@pytest.fixture(autouse=True)
def demo_provider():
    liqpay.set_client(liqpay.DemoLiqpayClient())
    yield
    liqpay.set_client(None)


def start_checkout(client, database, **data):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    response = client.post(f"/orders/{order.id}/pay", data=data, headers={"Accept": "application/json"})
    return get_order(database), response


def callback(client, payment: dict, private_key=None):
    data = liqpay.encode_data(payment)
    signature = liqpay.make_signature(private_key or liqpay.get_client().private_key, data)
    return client.post("/payments/liqpay/callback", data={"data": data, "signature": signature})


# ---------- signature ----------


def test_signature_is_base64_sha1_like_the_official_sdk():
    data = liqpay.encode_data({"version": 3, "action": "pay", "amount": "1"})
    expected = base64.b64encode(hashlib.sha1(("key" + data + "key").encode()).digest()).decode()
    assert liqpay.make_signature("key", data) == expected
    assert len(expected) == 28  # 20 bytes of SHA-1, like the samples in LiqPay's docs
    assert liqpay.signature_ok("key", data, expected)
    assert not liqpay.signature_ok("other", data, expected)


# ---------- checkout ----------


def test_pay_builds_a_signed_usd_checkout(client, database):
    order, response = start_checkout(client, database, tip_percent=10)
    checkout = response.json()["checkout"]
    params = liqpay.decode_data(checkout["data"])

    assert checkout["url"] == "/demo-liqpay/checkout"
    assert liqpay.signature_ok(liqpay.get_client().private_key, checkout["data"], checkout["signature"])
    assert params["action"] == "pay"
    assert params["version"] == 3
    assert params["currency"] == "USD"
    assert params["amount"] == "19.80"  # $18.00 donuts + $1.80 tip
    assert params["order_id"] == order.payment_reference
    assert params["result_url"].endswith(f"/orders/{order.id}/payment-return?t={order.access_token}")
    assert params["server_url"].endswith("/payments/liqpay/callback")
    assert order.payment_status == PaymentStatus.PENDING
    assert order.payment_amount == Decimal("19.80")


def test_without_javascript_the_page_posts_the_form_to_liqpay(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    page = client.post(f"/orders/{order.id}/pay")
    assert page.status_code == 200
    assert 'action="/demo-liqpay/checkout"' in page.text
    assert 'name="signature"' in page.text


def test_demo_checkout_rejects_a_forged_signature(client, database):
    _, response = start_checkout(client, database)
    checkout = response.json()["checkout"]
    forged = liqpay.encode_data({**liqpay.decode_data(checkout["data"]), "amount": "0.01"})
    result = client.post(checkout["url"], data={"data": forged, "signature": checkout["signature"]})
    assert result.status_code == 400


def test_every_attempt_gets_its_own_liqpay_order_id(client, database):
    order, first = start_checkout(client, database)
    client.post(f"/orders/{order.id}/pay", data={"tip_percent": 15}, headers={"Accept": "application/json"})
    again = get_order(database)
    assert again.payment_reference != order.payment_reference
    assert again.payment_amount == Decimal("20.70")


def test_full_demo_payment_and_declined_card(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    declined = pay_online(client, order.id, card=DECLINED_CARD)
    assert declined.headers["location"] == f"/orders/{order.id}/pay?declined=1"
    assert get_order(database).payment_status == PaymentStatus.FAILED

    paid = pay_online(client, order.id)
    assert paid.headers["location"] == f"/orders/{order.id}/receipt?paid=1"
    order = get_order(database)
    assert order.payment_status == PaymentStatus.PAID
    assert order.payment_provider_id


def test_manager_refund_goes_through_liqpay(client, database):
    test_sessions, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    pay_online(client, order.id)

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        assert client.post(f"/manager/orders/{order.id}/refund", data={"branch_id": ids["branch"]}).status_code == 303
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    order = get_order(database)
    assert order.payment_status == PaymentStatus.REFUNDED
    with test_sessions() as session:
        payment = session.scalar(select(DemoLiqpayPayment).where(DemoLiqpayPayment.order_id == order.payment_reference))
        assert payment.status == "reversed"


# ---------- callbacks (server_url) ----------


def paid_body(order, **changes):
    body = {"order_id": order.payment_reference, "status": "success", "amount": float(order.payment_amount),
            "currency": "USD", "payment_id": 123456, "action": "pay"}
    body.update(changes)
    return body


def test_signed_callback_marks_order_paid(client, database):
    order, _ = start_checkout(client, database)
    assert callback(client, paid_body(order)).status_code == 200
    order = get_order(database)
    assert order.payment_status == PaymentStatus.PAID
    assert order.payment_provider_id == "123456"


def test_callback_with_wrong_signature_is_rejected(client, database):
    order, _ = start_checkout(client, database)
    assert callback(client, paid_body(order), private_key="sandbox_not_ours").status_code == 400
    assert get_order(database).payment_status == PaymentStatus.PENDING


def test_callback_for_another_amount_or_old_attempt_is_ignored(client, database):
    order, _ = start_checkout(client, database)
    callback(client, paid_body(order, amount=0.01))
    callback(client, paid_body(order, currency="UAH"))
    callback(client, paid_body(order, order_id=f"donnie-{order.id}-old"))
    assert get_order(database).payment_status == PaymentStatus.PENDING


def test_failure_callback_never_undoes_a_payment(client, database):
    order, _ = start_checkout(client, database)
    callback(client, paid_body(order))
    callback(client, paid_body(order, status="failure", err_code="limit"))
    assert get_order(database).payment_status == PaymentStatus.PAID


# ---------- the real API client (with a mocked LiqPay) ----------


def test_real_client_status_and_refund_requests(client, database):
    keys = ("sandbox_i000", "sandbox_secret")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        assert liqpay.signature_ok(keys[1], form["data"], form["signature"])
        params = liqpay.decode_data(form["data"])
        requests.append(params)
        assert params["public_key"] == keys[0]
        if params["action"] == "status":
            return httpx.Response(200, json={"result": "ok", "status": "sandbox", "order_id": params["order_id"],
                                             "amount": 18.0, "currency": "USD", "payment_id": 777})
        if params["action"] == "refund":
            return httpx.Response(200, json={"result": "ok", "status": "reversed", "payment_id": 777})
        return httpx.Response(400, json={"result": "error"})

    liqpay.set_client(liqpay.LiqpayClient(*keys, transport=httpx.MockTransport(handler)))

    order, response = start_checkout(client, database)
    checkout = response.json()["checkout"]
    assert checkout["url"] == "https://www.liqpay.ua/api/3/checkout"
    assert liqpay.signature_ok(keys[1], checkout["data"], checkout["signature"])

    back = client.get(f"/orders/{order.id}/payment-return")
    assert back.headers["location"] == f"/orders/{order.id}/receipt?paid=1"
    assert requests[-1]["action"] == "status"
    assert get_order(database).payment_status == PaymentStatus.PAID

    _, ids = database
    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        client.post(f"/manager/orders/{order.id}/refund", data={"branch_id": ids["branch"]})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert requests[-1] == {**requests[-1], "action": "refund", "amount": "18.00"}
    assert get_order(database).payment_status == PaymentStatus.REFUNDED


def test_demo_payment_id_fits_postgres_integer(client, database):
    # demo_liqpay_payments.payment_id is INTEGER; SQLite doesn't enforce it,
    # PostgreSQL does, so a bigger id made demo payments fail there.
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    for _ in range(3):
        pay_online(client, order.id, card=DECLINED_CARD)
        assert 10**9 <= int(get_order(database).payment_provider_id) < 2**31
