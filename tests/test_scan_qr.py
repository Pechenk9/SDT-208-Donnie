"""The ticket's QR: a phone can open it, and the page says at once whether the order is paid."""
from app import liqpay, main
from app.models import OrderStatus

from test_orders import client, database  # noqa: F401  (pytest fixtures)
from test_payments import DECLINED_CARD, get_order, pay_online, place


def qr_url(page_text):
    marker = 'id="ticket-qr"'
    start = page_text.index(marker)
    url_start = page_text.index('data-url="', start) + len('data-url="')
    return page_text[url_start:page_text.index('"', url_start)].replace("&amp;", "&")


def test_qr_on_localhost_points_to_the_wifi_address(client, database, monkeypatch):
    monkeypatch.setattr(main, "_lan_ip", lambda: "192.168.0.170")
    _, ids = database
    place(client, ids)
    order = get_order(database)

    page = client.get(f"/en/orders/{order.id}/receipt", headers={"host": "127.0.0.1:8002"})

    assert qr_url(page.text) == (
        f"http://192.168.0.170:8002/en/orders/{order.id}/receipt?t={order.access_token}&scan=1"
    )


def test_public_base_url_wins(client, database, monkeypatch):
    monkeypatch.setattr(liqpay, "PUBLIC_BASE_URL", "https://donnie.example.com")
    _, ids = database
    place(client, ids)
    order = get_order(database)

    page = client.get(f"/en/orders/{order.id}/receipt", headers={"host": "127.0.0.1:8002"})

    assert qr_url(page.text).startswith(f"https://donnie.example.com/en/orders/{order.id}/receipt?t=")


def test_real_host_is_kept(client, database, monkeypatch):
    monkeypatch.setattr(main, "_lan_ip", lambda: "192.168.0.170")
    _, ids = database
    place(client, ids)
    order = get_order(database)

    page = client.get(f"/en/orders/{order.id}/receipt")  # host: testserver

    assert qr_url(page.text).startswith("http://testserver/en/orders/")


def scan(client, order):
    client.cookies.clear()  # a phone that never saw this order
    return client.get(f"/en/orders/{order.id}/receipt?t={order.access_token}&scan=1")


def test_scan_of_paid_order_says_paid(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    pay_online(client, order.id)
    order = get_order(database)

    page = scan(client, order)

    assert page.status_code == 200
    assert "scan-check--ok" in page.text
    assert "Paid online with LiqPay" in page.text
    assert "₴18.00" in page.text
    assert "Thank you for your order!" not in page.text


def test_scan_of_pay_at_pickup_order_says_collect_money(client, database):
    _, ids = database
    place(client, ids)
    page = scan(client, get_order(database))

    assert "scan-check--due" in page.text
    assert "Not paid yet" in page.text
    assert "Collect the money at pickup" in page.text


def test_scan_of_declined_payment_says_not_paid(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    pay_online(client, order.id, card=DECLINED_CARD)

    page = scan(client, get_order(database))

    assert "scan-check--stop" in page.text
    assert "The online payment was declined." in page.text


def test_scan_of_cancelled_order_says_do_not_hand_out(client, database):
    test_sessions, ids = database
    place(client, ids)
    with test_sessions() as session:
        order = session.get(main.Order, get_order(database).id)
        order.status = OrderStatus.CANCELLED
        session.commit()

    page = scan(client, get_order(database))

    assert "scan-check--stop" in page.text
    assert "Do not hand it out." in page.text


def test_scan_without_token_is_still_404(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)
    client.cookies.clear()
    assert client.get(f"/en/orders/{order.id}/receipt?scan=1").status_code == 404


def test_normal_receipt_has_no_scan_banner(client, database):
    _, ids = database
    place(client, ids)
    page = client.get(f"/en/orders/{get_order(database).id}/receipt")
    assert 'class="scan-check' not in page.text
