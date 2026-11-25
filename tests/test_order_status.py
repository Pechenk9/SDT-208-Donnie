"""Manager status buttons and the live status endpoint behind the receipt tracker."""
from app.deps import get_current_user
from app.main import app
from app.models import Branch, OrderStatus, UserRole

# Reuse the order test database (one branch, one 3.00 donut), client and helpers.
from test_orders import client, database  # noqa: F401  (pytest fixtures)
from test_payments import _login_as, get_order, place


def move(client, ids, order_id, action, branch_id=None):
    return client.post(
        f"/manager/orders/{order_id}/status",
        data={"branch_id": branch_id or ids["branch"], "action": action},
    )


def test_manager_walks_an_order_through_every_step(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        dashboard = client.get("/en/manager")
        assert "Next: Baking" in dashboard.text

        expected = [OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.COMPLETED]
        for status in expected:
            response = move(client, ids, order.id, "next")
            assert response.status_code == 303
            assert "notice=order-status" in response.headers["location"]
            assert get_order(database).status == status

        # Done is the last step.
        assert move(client, ids, order.id, "next").status_code == 400
        assert move(client, ids, order.id, "cancel").status_code == 400

        # Back undoes a mistake.
        assert move(client, ids, order.id, "back").status_code == 303
        assert get_order(database).status == OrderStatus.READY
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_back_stops_at_the_first_step_and_cancel_is_final(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        assert move(client, ids, order.id, "back").status_code == 400
        assert move(client, ids, order.id, "dance").status_code == 400

        assert move(client, ids, order.id, "cancel").status_code == 303
        assert get_order(database).status == OrderStatus.CANCELLED
        assert move(client, ids, order.id, "next").status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_customer_and_other_branch_manager_cannot_change_status(client, database):
    test_sessions, ids = database
    place(client, ids)
    order = get_order(database)

    _login_as(database, UserRole.CUSTOMER)
    try:
        assert move(client, ids, order.id, "next").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    with test_sessions() as session:
        other = Branch(code="OTHER", name="Other", city="Lviv", address="B")
        session.add(other)
        session.commit()
        other_id = other.id

    _login_as(database, UserRole.MANAGER, other_id)
    try:
        assert move(client, ids, order.id, "next", branch_id=other_id).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert get_order(database).status == OrderStatus.PENDING


def test_status_endpoint_follows_manager_changes(client, database):
    _, ids = database
    place(client, ids)
    order = get_order(database)

    data = client.get(f"/orders/{order.id}/status").json()
    assert data["status"] == "pending"
    assert data["progress"]["current"] == 0

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        move(client, ids, order.id, "next")
        data = client.get(f"/orders/{order.id}/status").json()
        assert data["status"] == "preparing"
        assert data["progress"]["current"] == 1
        assert "oven" in data["progress"]["hint"]

        move(client, ids, order.id, "cancel")
        data = client.get(f"/orders/{order.id}/status").json()
        assert data == {"status": "cancelled", "progress": None}
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert client.get("/orders/999999/status").status_code == 404


def test_unpaid_online_order_cannot_go_to_the_kitchen(client, database):
    from test_payments import pay_online

    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    _login_as(database, UserRole.MANAGER, ids["branch"])
    try:
        dashboard = client.get("/en/manager")
        assert "Next: Baking" not in dashboard.text
        assert move(client, ids, order.id, "next").status_code == 400
        assert get_order(database).status == OrderStatus.PENDING

        # Cancelling an abandoned online order is still allowed.
        assert 'value="cancel"' in dashboard.text

        pay_online(client, order.id)
        assert "Next: Baking" in client.get("/en/manager").text
        assert move(client, ids, order.id, "next").status_code == 303
        assert get_order(database).status == OrderStatus.PREPARING
    finally:
        app.dependency_overrides.pop(get_current_user, None)
