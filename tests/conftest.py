"""Shared test setup.

Tests always pay through the built-in LiqPay emulator, even when .env holds
real LiqPay keys, so running the suite never talks to liqpay.ua. Emails
always go to a temporary outbox folder, never to a real mail server.
"""
import pytest

from app import liqpay, mailer


@pytest.fixture(autouse=True)
def email_outbox(monkeypatch, tmp_path):
    outbox = tmp_path / "outbox"
    monkeypatch.setattr(mailer, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    monkeypatch.setattr(mailer, "OUTBOX_DIR", outbox)
    return outbox


@pytest.fixture(autouse=True)
def liqpay_demo_mode(monkeypatch):
    monkeypatch.setattr(liqpay, "PAYMENT_PROVIDER", "demo")
    monkeypatch.setattr(liqpay, "LIQPAY_PUBLIC_KEY", "")
    monkeypatch.setattr(liqpay, "LIQPAY_PRIVATE_KEY", "")
    monkeypatch.setattr(liqpay, "PUBLIC_BASE_URL", "")
    liqpay.set_client(liqpay.DemoLiqpayClient())
    yield
    liqpay.set_client(None)
