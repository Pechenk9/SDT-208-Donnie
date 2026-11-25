"""The payment receipt goes to the email given at checkout, exactly once."""
import email
import smtplib
from email import policy

from app import mailer
from app.deps import get_current_user
from app.main import app
from app.models import Order, PaymentStatus, UserRole

from test_orders import client, database  # noqa: F401  (pytest fixtures)
from test_payments import DECLINED_CARD, _login_as, get_order, pay_online, place
from test_liqpay import callback, paid_body


def letters(outbox):
    if not outbox.exists():
        return []
    return [
        email.message_from_bytes(path.read_bytes(), policy=policy.default)
        for path in sorted(outbox.glob("*.eml"))
    ]


def text_of(letter):
    return letter.get_body(preferencelist=("plain",)).get_content()


def html_of(letter):
    return letter.get_body(preferencelist=("html",)).get_content()


def test_paid_order_emails_one_receipt(client, database, email_outbox):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com")
    order = get_order(database)

    # The demo callback and the return page both see the payment: one letter.
    assert pay_online(client, order.id, tip_percent=10).status_code == 303
    client.get(f"/en/orders/{order.id}/receipt?paid=1")

    sent = letters(email_outbox)
    assert len(sent) == 1
    letter = sent[0]
    assert letter["To"] == "guest@example.com"
    assert letter["Subject"] == f"Donnie: receipt for order #{order.id}"
    body = text_of(letter)
    assert "Test Donut × 6" in body
    assert "₴18.00" in body       # 6 × ₴3.00
    assert "₴1.80" in body        # 10% tip
    assert "Paid: ₴19.80 (UAH," in body
    assert "(Kyiv time)" in body
    order = get_order(database)
    link = f"http://testserver/en/orders/{order.id}/receipt?t={order.access_token}"
    assert link in body
    assert f'href="{link}"' in html_of(letter)
    assert order.receipt_emailed_at is not None

    # The link works on another device, with no cookie from the checkout.
    client.cookies.clear()
    page = client.get(link)
    assert page.status_code == 200
    assert f"Order<br>#{order.id}" in page.text


def test_repeated_liqpay_callbacks_do_not_send_again(client, database, email_outbox):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com")
    order = get_order(database)
    client.post(f"/orders/{order.id}/pay", headers={"Accept": "application/json"})
    order = get_order(database)

    assert callback(client, paid_body(order)).status_code == 200
    assert callback(client, paid_body(order)).status_code == 200
    client.get(f"/orders/{order.id}/payment-return")

    assert len(letters(email_outbox)) == 1
    test_sessions, _ = database
    with test_sessions() as session:
        assert session.query(Order).count() == 1


def test_declined_card_sends_nothing(client, database, email_outbox):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com")
    order = get_order(database)

    pay_online(client, order.id, card=DECLINED_CARD)

    assert get_order(database).payment_status == PaymentStatus.FAILED
    assert letters(email_outbox) == []


def test_order_without_email_sends_nothing(client, database, email_outbox):
    _, ids = database
    place(client, ids, payment_method="online")
    order = get_order(database)

    pay_online(client, order.id)

    assert get_order(database).payment_status == PaymentStatus.PAID
    assert letters(email_outbox) == []


def test_pay_on_receipt_order_sends_nothing(client, database, email_outbox):
    _, ids = database
    place(client, ids, customer_email="guest@example.com")
    order = get_order(database)

    client.get(f"/en/orders/{order.id}/receipt")

    assert letters(email_outbox) == []


def test_signed_in_guest_without_email_gets_it_at_the_account_address(client, database, email_outbox):
    _, ids = database
    _login_as(database, UserRole.CUSTOMER)
    try:
        place(client, ids, payment_method="online")
        order = get_order(database)
        pay_online(client, order.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    sent = letters(email_outbox)
    assert [letter["To"] for letter in sent] == ["customer@example.com"]


def test_mail_error_keeps_the_payment_and_retries_later(client, database, email_outbox, monkeypatch):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com")
    order = get_order(database)

    def broken(message):
        raise smtplib.SMTPServerDisconnected("mail server is down")

    monkeypatch.setattr(mailer, "send", broken)
    result = pay_online(client, order.id)

    assert result.headers["location"] == f"/en/orders/{order.id}/receipt?paid=1"
    order = get_order(database)
    assert order.payment_status == PaymentStatus.PAID
    assert order.receipt_emailed_at is None  # free to try again

    monkeypatch.undo()
    monkeypatch.setattr(mailer, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(mailer, "OUTBOX_DIR", email_outbox)
    client.get(f"/en/orders/{order.id}/receipt")

    assert len(letters(email_outbox)) == 1
    assert get_order(database).receipt_emailed_at is not None


def test_html_letter_escapes_what_the_guest_typed(client, database, email_outbox):
    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com",
          customer_name="<b>Eve</b>")
    order = get_order(database)

    pay_online(client, order.id)

    html = html_of(letters(email_outbox)[0])
    assert "<b>Eve</b>" not in html
    assert "&lt;b&gt;Eve&lt;/b&gt;" in html


def test_smtp_mode_uses_starttls_and_login(monkeypatch, client, database):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, message):
            calls.append(("send", message["To"]))

    monkeypatch.setattr(mailer, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(mailer, "SMTP_PORT", 587)
    monkeypatch.setattr(mailer, "SMTP_USER", "donnie")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    _, ids = database
    place(client, ids, payment_method="online", customer_email="guest@example.com")
    pay_online(client, get_order(database).id)

    assert calls == [
        ("connect", "smtp.example.com", 587),
        ("starttls",),
        ("login", "donnie"),
        ("send", "guest@example.com"),
    ]


def test_paid_time_is_shown_in_kyiv_time():
    from datetime import datetime, timezone
    # 22:18 UTC on 22 Nov is 00:18 on 23 Nov in Kyiv (UTC+2 in winter).
    assert mailer.kyiv_time(datetime(2026, 11, 22, 22, 18, tzinfo=timezone.utc)) == "23 Nov 2026, 00:18"
    assert mailer.kyiv_time(datetime(2026, 11, 22, 22, 18)) == "23 Nov 2026, 00:18"  # naive = UTC
    assert mailer.kyiv_time(None) is None
