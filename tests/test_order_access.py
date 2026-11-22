"""Order ids are sequential: the receipt, payment and status pages open only
for the browser that placed the order, the emailed link (?t=), the account
that placed it, the owner and the managers of its branch."""
from sqlalchemy import select

from app.deps import get_current_user
from app.main import app
from app.models import Branch, Order, User, UserRole

from test_orders import client, database  # noqa: F401  (pytest fixtures)
from test_payments import _login_as, get_order, pay_online, place

PAGES = ("/receipt", "/pay", "/status")


def stranger(client):
    client.cookies.clear()
    return client


def test_browser_that_placed_the_order_can_open_it(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    for page in PAGES:
        assert client.get(f"/orders/{order.id}{page}").status_code == 200
    assert pay_online(client, order.id).headers["location"] == f"/orders/{order.id}/receipt?paid=1"
    assert client.get(f"/orders/{order.id}/receipt?paid=1").status_code == 200


def test_stranger_guessing_the_number_gets_404(client, database):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com",
          delivery_address="Secret street 1", fulfillment_type="delivery")
    order = get_order(database)

    stranger(client)
    for page in PAGES:
        response = client.get(f"/orders/{order.id}{page}")
        assert response.status_code == 404, page
        assert "Secret street" not in response.text
    assert client.post(f"/orders/{order.id}/pay", data={"tip_percent": 15}).status_code == 404
    assert client.get(f"/orders/{order.id}/receipt?t=wrong-token").status_code == 404
    assert client.get(f"/orders/{order.id}/receipt?t=ключ").status_code == 404  # non-ASCII
    assert get_order(database).tip_amount == 0  # the stranger couldn't touch the tip


def test_link_with_token_opens_and_remembers_the_order(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)

    stranger(client)
    page = client.get(f"/orders/{order.id}/receipt?t={order.access_token}")
    assert page.status_code == 200
    # The live tracker and the pickup QR carry the token too.
    assert f'data-status-url="/orders/{order.id}/status?t={order.access_token}"' in page.text
    assert f"orders/{order.id}/receipt?t={order.access_token}" in page.text
    # And the browser remembers it: the plain address works from now on.
    assert client.get(f"/orders/{order.id}/status").status_code == 200


def test_return_from_liqpay_restores_access_without_the_cookie(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)
    start = client.post(f"/orders/{order.id}/pay", headers={"Accept": "application/json"})
    checkout = start.json()["checkout"]
    opened = client.post(checkout["url"], data={"data": checkout["data"], "signature": checkout["signature"]})
    paid = client.post(opened.headers["location"], data={"card": "4242424242424242"})

    stranger(client)  # e.g. the browser dropped our cookie while on LiqPay
    back = client.get(paid.headers["location"])
    assert back.headers["location"] == f"/orders/{order.id}/receipt?paid=1"
    assert client.get(back.headers["location"]).status_code == 200


def test_return_page_without_token_gives_no_access(client, database):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    stranger(client)
    back = client.get(f"/orders/{order.id}/payment-return")
    assert back.status_code == 303
    assert client.get(back.headers["location"]).status_code == 404


def test_account_that_placed_the_order_opens_it_anywhere(client, database):
    _, ids = database
    _login_as(database, UserRole.CUSTOMER)
    try:
        place(client, ids)
        order = get_order(database)
        stranger(client)
        assert client.get(f"/orders/{order.id}/receipt").status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_another_customer_cannot_open_it(client, database):
    test_sessions, ids = database
    place(client, ids)
    order = get_order(database)

    stranger(client)
    _login_as(database, UserRole.CUSTOMER)
    try:
        assert client.get(f"/orders/{order.id}/receipt").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_branch_manager_and_owner_open_it(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)
    stranger(client)

    for role, branch in ((UserRole.MANAGER, ids["branch"]), (UserRole.OWNER, None)):
        _login_as(database, role, branch)
        try:
            assert client.get(f"/orders/{order.id}/receipt").status_code == 200, role
        finally:
            app.dependency_overrides.pop(get_current_user, None)


def test_manager_of_another_branch_cannot_open_it(client, database):
    test_sessions, ids = database
    place(client, ids)
    order = get_order(database)
    with test_sessions() as session:
        other = Branch(code="OTHER", name="Other Branch", city="Lviv", address="Elsewhere")
        session.add(other)
        session.commit()
        other_id = other.id

    stranger(client)
    _login_as(database, UserRole.MANAGER, other_id)
    try:
        assert client.get(f"/orders/{order.id}/receipt").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_every_order_gets_its_own_long_token(client, database):
    test_sessions, ids = database
    place(client, ids)
    place(client, ids)
    with test_sessions() as session:
        tokens = session.scalars(select(Order.access_token)).all()
    assert len(set(tokens)) == 2
    assert all(len(token) >= 32 for token in tokens)
