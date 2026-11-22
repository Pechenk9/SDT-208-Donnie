"""Shared test setup.

Tests always pay through the built-in LiqPay emulator, even when .env holds
real LiqPay keys, so running the suite never talks to liqpay.ua.
"""
import pytest

from app import liqpay


@pytest.fixture(autouse=True)
def liqpay_demo_mode(monkeypatch):
    monkeypatch.setattr(liqpay, "PAYMENT_PROVIDER", "demo")
    monkeypatch.setattr(liqpay, "LIQPAY_PUBLIC_KEY", "")
    monkeypatch.setattr(liqpay, "LIQPAY_PRIVATE_KEY", "")
    monkeypatch.setattr(liqpay, "PUBLIC_BASE_URL", "")
    liqpay.set_client(liqpay.DemoLiqpayClient())
    yield
    liqpay.set_client(None)
