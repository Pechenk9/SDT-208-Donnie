import pytest

from test_orders import client, database  # noqa: F401  (pytest fixtures)


@pytest.mark.parametrize(
    ("legacy_path", "english_path"),
    [
        ("/", "/en/"),
        ("/login", "/en/login"),
        ("/register", "/en/register"),
        ("/profile", "/en/profile"),
        ("/manager", "/en/manager"),
        ("/owner", "/en/owner"),
        ("/contacts", "/en/contacts"),
        ("/store", "/en/store"),
        ("/product/7", "/en/product/7"),
        ("/order", "/en/order"),
        ("/table", "/en/table"),
        ("/orders/7/receipt", "/en/orders/7/receipt"),
        ("/orders/7/pay", "/en/orders/7/pay"),
        ("/demo-liqpay/pay/demo-ref", "/en/demo-liqpay/pay/demo-ref"),
    ],
)
def test_legacy_page_redirect_preserves_the_complete_query(
    client, database, legacy_path, english_path
):
    query = "campaign=qr&tag=one&tag=two&note=two%20words"

    response = client.get(f"{legacy_path}?{query}")

    assert response.status_code == 307
    assert response.headers["location"] == f"{english_path}?{query}"


def test_legacy_store_and_table_redirects_keep_qr_context(client, database):
    query = "branch=TEST&table=12&tag=one&tag=two"

    store_redirect = client.get(f"/store?{query}")
    assert store_redirect.status_code == 307
    assert store_redirect.headers["location"] == f"/en/store?{query}"
    store_page = client.get(store_redirect.headers["location"])
    assert store_page.status_code == 200
    assert str(store_page.url).endswith(f"/en/store?{query}")
    assert "js/branch.js" in store_page.text

    table_redirect = client.get(f"/table?{query}")
    assert table_redirect.status_code == 307
    assert table_redirect.headers["location"] == f"/en/table?{query}"
    table_page = client.get(table_redirect.headers["location"])
    assert table_page.status_code == 200
    assert str(table_page.url).endswith(f"/en/table?{query}")
    assert "js/branch.js" in table_page.text
    assert "js/table.js" in table_page.text
