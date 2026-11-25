import json
import re
from urllib.parse import urlparse

from app.main import _localized_month_text, short_date
from app.models import Branch, Ingredient, Product, User, UserRole
from app.security import hash_password

from test_orders import client, database  # noqa: F401


def _script_json(html: str, script_id: str) -> dict:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_ukrainian_date_labels_are_localized():
    from datetime import date

    assert short_date(date(2026, 1, 2), "ua") == "пт, 2 січ"
    assert _localized_month_text("23 Nov 2026, 00:18", "ua") == "23 лист 2026, 00:18"


def test_language_switcher_keeps_current_page_and_query(client, database):
    _, ids = database
    query = "campaign=qr&tag=one&tag=two"

    ukrainian = client.get(f"/ua/product/{ids['product']}?{query}")
    assert ukrainian.status_code == 200
    assert '<html lang="uk">' in ukrainian.text
    html_query = query.replace("&", "&amp;")
    assert f'href="/en/product/{ids["product"]}?{html_query}"' in ukrainian.text

    english = client.get(f"/en/product/{ids['product']}?{query}")
    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert f'href="/ua/product/{ids["product"]}?{html_query}"' in english.text

    fallback = client.get("/ua/login?next=%2Fua%2Fprofile")
    assert 'href="/en/login?next=%2Fua%2Fprofile"' in fallback.text


def test_ua_routes_render_pages_and_keep_auth_redirects_localized(client, database):
    _, ids = database
    for path in (
        "/ua/",
        "/ua/login",
        "/ua/register",
        "/ua/contacts",
        "/ua/store",
        f"/ua/product/{ids['product']}",
        "/ua/order",
        "/ua/table",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert '<html lang="uk">' in response.text, path

    profile = client.get("/ua/profile")
    assert profile.status_code == 303
    assert profile.headers["location"] == "/ua/login"
    assert client.get("/ua/manager").headers["location"] == "/ua/login"
    assert client.get("/ua/owner").headers["location"] == "/ua/login"


def test_localized_catalogue_fields_and_missing_translation_fallbacks(
    client, database
):
    test_sessions, ids = database
    with test_sessions() as session:
        product = session.get(Product, ids["product"])
        ingredient = session.get(Ingredient, ids["ingredient_a"])
        fallback_ingredient = session.get(Ingredient, ids["ingredient_b"])
        branch = session.get(Branch, ids["branch"])
        product.name = "Пончик тест"
        product.name_en = "Test Donut"
        product.description = None
        product.description_en = "English product description"
        ingredient.name = "Крем"
        ingredient.name_en = "Cream"
        ingredient.description = "Український опис крему"
        ingredient.description_en = "English cream description"
        fallback_ingredient.name = "Українська начинка"
        fallback_ingredient.name_en = None
        branch.city = "Київ"
        branch.city_en = "Kyiv"
        branch.address = "Українська адреса"
        branch.address_en = "English address"
        session.commit()

    english_store = _script_json(
        client.get("/en/store").text, "store-data"
    )
    ukrainian_store = _script_json(
        client.get("/ua/store").text, "store-data"
    )
    assert english_store["products"][0]["name"] == "Test Donut"
    assert (
        english_store["products"][0]["description"]
        == "English product description"
    )
    assert ukrainian_store["products"][0]["name"] == "Пончик тест"
    assert (
        ukrainian_store["products"][0]["description"]
        == "English product description"
    )

    english_product = _script_json(
        client.get(f"/en/product/{ids['product']}").text, "product-data"
    )
    ukrainian_product = _script_json(
        client.get(f"/ua/product/{ids['product']}").text, "product-data"
    )
    english_cream = next(
        item for item in english_product["ingredients"] if item["id"] == ids["ingredient_a"]
    )
    ukrainian_cream = next(
        item for item in ukrainian_product["ingredients"] if item["id"] == ids["ingredient_a"]
    )
    assert english_cream["name"] == "Cream"
    assert ukrainian_cream["name"] == "Крем"
    assert ukrainian_cream["description"] == "Український опис крему"
    assert any(
        item["name"] == "Українська начинка"
        for item in english_product["ingredients"]
    )

    branches = client.get("/en/api/branches").json()
    ukrainian_branches = client.get("/ua/api/branches").json()
    assert branches[0]["city"] == "Kyiv"
    assert branches[0]["address"] == "English address"
    assert ukrainian_branches[0]["city"] == "Київ"
    assert ukrainian_branches[0]["address"] == "Українська адреса"


def test_ua_login_and_registration_use_prefixed_post_handlers(client, database):
    test_sessions, _ = database
    with test_sessions() as session:
        session.add(
            User(
                first_name="Test",
                last_name="Customer",
                email="customer@example.com",
                password_hash=hash_password("valid-password"),
                role=UserRole.CUSTOMER,
            )
        )
        session.commit()

    invalid = client.post(
        "/ua/register",
        data={"email": "not-an-email", "password": "short"},
    )
    assert invalid.status_code == 400
    assert "Вкажіть ім’я." in invalid.text
    assert "Вкажіть дійсну адресу електронної пошти." in invalid.text

    login = client.post(
        "/ua/login",
        data={"email": "customer@example.com", "password": "valid-password"},
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/ua/profile"
    assert client.get("/ua/profile").status_code == 200

    logout = client.post("/ua/logout")
    assert logout.status_code == 303
    assert logout.headers["location"] == "/ua/store"
    assert client.get("/ua/profile").headers["location"] == "/ua/login"

    registration = client.post(
        "/ua/register",
        data={
            "first_name": "New",
            "last_name": "Customer",
            "email": "new-customer@example.com",
            "password": "valid-password",
            "confirm_password": "valid-password",
        },
    )
    assert registration.status_code == 303
    assert registration.headers["location"] == "/ua/profile"
    assert client.get("/ua/profile").status_code == 200


def test_ua_online_checkout_preserves_language_on_success_and_decline(
    client, database
):
    _, ids = database
    response = client.post(
        "/ua/orders",
        data={
            "customer_name": "Test Customer",
            "customer_phone": "0671234567",
            "branch_id": str(ids["branch"]),
            "fulfillment_type": "pickup",
            "payment_method": "online",
            "items_json": json.dumps(
                [{"product_id": ids["product"], "quantity": 6, "ingredients": []}]
            ),
        },
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/ua/orders/")
    order_id = int(
        re.search(r"/orders/(\d+)/pay", response.headers["location"]).group(1)
    )

    def finish_demo_payment(card_number):
        start = client.post(
            f"/ua/orders/{order_id}/pay",
            headers={"Accept": "application/json"},
        )
        assert start.status_code == 200
        checkout = start.json()["checkout"]
        opened = client.post(
            checkout["url"],
            data={"data": checkout["data"], "signature": checkout["signature"]},
        )
        assert opened.status_code == 303
        assert opened.headers["location"].startswith("/ua/demo-liqpay/pay/")
        page = client.get(opened.headers["location"])
        assert page.status_code == 200
        assert '<html lang="uk">' in page.text
        assert "₴" in page.text
        assert "UAH" in page.text
        assert "USD" not in page.text
        reference = urlparse(opened.headers["location"]).path.rsplit("/", 1)[-1]
        result = client.post(
            f"/ua/demo-liqpay/pay/{reference}",
            data={"card": card_number},
        )
        assert result.status_code == 303
        assert urlparse(result.headers["location"]).path == (
            f"/ua/orders/{order_id}/payment-return"
        )
        return client.get(result.headers["location"])

    declined = finish_demo_payment("4000000000000002")
    assert declined.status_code == 303
    assert declined.headers["location"] == f"/ua/orders/{order_id}/pay?declined=1"

    paid = finish_demo_payment("4242424242424242")
    assert paid.status_code == 303
    assert paid.headers["location"] == f"/ua/orders/{order_id}/receipt?paid=1"
    receipt = client.get(paid.headers["location"])
    assert receipt.status_code == 200
    assert '<html lang="uk">' in receipt.text
    assert "₴18.00" in receipt.text
