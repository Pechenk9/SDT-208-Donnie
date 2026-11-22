"""LiqPay internet acquiring: checkout, callbacks, payment status and refunds.

Two modes, chosen with PAYMENT_PROVIDER in .env:

- "demo" (default): a built-in emulator of the LiqPay checkout. It checks
  the same data + signature, shows its own page at /demo-liqpay/checkout,
  sends the same signed callback and answers status and refund requests.
  No LiqPay account, no card details, no real money.
- "liqpay": the real LiqPay with LIQPAY_PUBLIC_KEY and LIQPAY_PRIVATE_KEY.
  Use the sandbox keys from your LiqPay account (they start with
  "sandbox_"): LiqPay then shows its real checkout page, accepts test
  cards such as 4242 4242 4242 4242 and moves no money.

How LiqPay works (https://www.liqpay.ua/en/doc):
  data      = base64(JSON with version, public_key, action, amount, ...)
  signature = base64(sha1(private_key + data + private_key))
The browser POSTs data + signature to https://www.liqpay.ua/api/3/checkout.
LiqPay POSTs the result (data + signature) to server_url and sends the guest
back to result_url. Status and refund are POSTs to /api/request.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DemoLiqpayPayment, Order, PaymentStatus

CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"
REQUEST_URL = "https://www.liqpay.ua/api/request"
API_VERSION = 3
CURRENCY = "USD"  # LiqPay accepts USD, EUR and UAH; Donnie's menu is in dollars

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "demo").strip().lower()
LIQPAY_PUBLIC_KEY = os.getenv("LIQPAY_PUBLIC_KEY", "").strip()
LIQPAY_PRIVATE_KEY = os.getenv("LIQPAY_PRIVATE_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Statuses that mean the money is taken. LiqPay's sandbox reports test
# payments as "sandbox".
PAID_STATUSES = {"success", "sandbox", "wait_accept", "wait_compensation"}
FAILED_STATUSES = {"failure", "error"}


class LiqpayError(Exception):
    """LiqPay refused a request or could not be reached."""


def is_demo() -> bool:
    return PAYMENT_PROVIDER != "liqpay" or not (LIQPAY_PUBLIC_KEY and LIQPAY_PRIVATE_KEY)


def is_sandbox() -> bool:
    return is_demo() or LIQPAY_PUBLIC_KEY.startswith("sandbox_")


# ---------- data and signature (same as LiqPay's official SDK) ----------


def encode_data(params: dict) -> str:
    return base64.b64encode(json.dumps(params).encode()).decode()


def decode_data(data: str) -> dict:
    return json.loads(base64.b64decode(data))


def make_signature(private_key: str, data: str) -> str:
    raw = (private_key + data + private_key).encode()
    return base64.b64encode(hashlib.sha1(raw).digest()).decode()


def signature_ok(private_key: str, data: str, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(make_signature(private_key, data), signature)


@dataclass(frozen=True)
class Checkout:
    url: str
    data: str
    signature: str


# ---------- the real LiqPay ----------


class LiqpayClient:
    def __init__(self, public_key: str, private_key: str,
                 transport: httpx.BaseTransport | None = None):
        self.public_key = public_key
        self.private_key = private_key
        self._transport = transport
        self._http_client: httpx.Client | None = None

    @property
    def _http(self) -> httpx.Client:
        # Created on first use: the demo emulator never needs it.
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=15, transport=self._transport)
        return self._http_client

    checkout_url = CHECKOUT_URL

    def checkout(self, *, order_id: str, amount: Decimal, description: str,
                 result_url: str, server_url: str | None) -> Checkout:
        params = {
            "version": API_VERSION,
            "public_key": self.public_key,
            "action": "pay",
            "amount": str(amount),
            "currency": CURRENCY,
            "description": description,
            "order_id": order_id,
            "result_url": result_url,
            "language": "en",
        }
        if server_url:
            params["server_url"] = server_url
        data = encode_data(params)
        return Checkout(self.checkout_url, data, make_signature(self.private_key, data))

    def _api(self, params: dict) -> dict:
        params = {"version": API_VERSION, "public_key": self.public_key, **params}
        data = encode_data(params)
        try:
            response = self._http.post(
                REQUEST_URL,
                data={"data": data, "signature": make_signature(self.private_key, data)},
            )
        except httpx.HTTPError as error:
            raise LiqpayError(f"LiqPay is not reachable: {error}") from error
        if response.status_code >= 400:
            raise LiqpayError(f"LiqPay {response.status_code}: {response.text}")
        try:
            result = response.json()
        except ValueError as error:
            raise LiqpayError("LiqPay sent an unreadable answer") from error
        if result.get("result") == "error" and result.get("status") not in FAILED_STATUSES:
            raise LiqpayError(f"LiqPay error: {result.get('err_description') or result}")
        return result

    def status(self, session: Session, order_id: str) -> dict:
        return self._api({"action": "status", "order_id": order_id})

    def refund(self, session: Session, order_id: str, amount: Decimal) -> dict:
        return self._api({"action": "refund", "order_id": order_id, "amount": str(amount)})


# ---------- the demo emulator ----------


class DemoLiqpayClient(LiqpayClient):
    """Plays LiqPay's part inside Donnie, with its own sandbox keys."""

    checkout_url = "/demo-liqpay/checkout"

    def __init__(self):
        super().__init__(
            "sandbox_demo_" + secrets.token_hex(6),
            "sandbox_demo_" + secrets.token_hex(16),
        )

    def open_checkout(self, session: Session, data: str, signature: str) -> DemoLiqpayPayment:
        """What LiqPay does when the browser POSTs the checkout form."""
        if not signature_ok(self.private_key, data, signature):
            raise LiqpayError("Invalid signature")
        params = decode_data(data)
        if params.get("public_key") != self.public_key or params.get("action") != "pay":
            raise LiqpayError("Invalid checkout data")

        payment = self.get_payment(session, params["order_id"])
        if payment is None:
            now = _now()
            payment = DemoLiqpayPayment(
                order_id=params["order_id"],
                amount=Decimal(str(params["amount"])),
                currency=params["currency"],
                description=params.get("description", ""),
                status="created",
                result_url=params.get("result_url", "/"),
                server_url=params.get("server_url"),
                create_date=now,
                end_date=now,
            )
            session.add(payment)
            session.flush()
        return payment

    def get_payment(self, session: Session, order_id: str) -> DemoLiqpayPayment | None:
        return session.scalar(select(DemoLiqpayPayment).where(DemoLiqpayPayment.order_id == order_id))

    def pay(self, session: Session, payment: DemoLiqpayPayment, card: str) -> None:
        """The guest picked a test card on the demo page. Same test cards as
        LiqPay's sandbox: 4242… succeeds, 4000…0002 is declined."""
        payment.end_date = _now()
        payment.payment_id = payment.payment_id or secrets.randbelow(9 * 10**9) + 10**9
        payment.card_mask = f"{card[:6]}*{card[-2:]}"
        if card == "4000000000000002":
            payment.status = "failure"
            payment.err_code = "limit"
            payment.err_description = "Card limit exceeded (test card)"
        else:
            payment.status = "sandbox"
            payment.err_code = None
            payment.err_description = None
        self._callback(session, payment)

    def status(self, session: Session, order_id: str) -> dict:
        payment = self.get_payment(session, order_id)
        if payment is None:
            return {"result": "error", "status": "error", "err_code": "payment_not_found",
                    "order_id": order_id}
        return self._payment_body(payment)

    def refund(self, session: Session, order_id: str, amount: Decimal) -> dict:
        payment = self.get_payment(session, order_id)
        if payment is None or payment.status not in PAID_STATUSES:
            raise LiqpayError("LiqPay error: payment can't be refunded")
        payment.status = "reversed"
        payment.end_date = _now()
        self._callback(session, payment)
        return {"result": "ok", "status": "reversed", "payment_id": payment.payment_id,
                "action": "refund", "wait_amount": False}

    def _payment_body(self, payment: DemoLiqpayPayment) -> dict:
        body = {
            "result": "ok",
            "action": "pay",
            "version": API_VERSION,
            "public_key": self.public_key,
            "payment_id": payment.payment_id,
            "status": payment.status,
            "order_id": payment.order_id,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "description": payment.description,
            "paytype": "card",
            "create_date": payment.create_date,
            "end_date": payment.end_date,
        }
        if payment.card_mask:
            body["sender_card_mask2"] = payment.card_mask
        if payment.err_code:
            body["err_code"] = payment.err_code
            body["err_description"] = payment.err_description
        return body

    def _callback(self, session: Session, payment: DemoLiqpayPayment) -> None:
        # The real LiqPay POSTs data + signature to server_url. Here it goes
        # straight to the same handler, so the signature check runs as well.
        if not payment.server_url:
            return
        data = encode_data(self._payment_body(payment))
        handle_callback(session, data, make_signature(self.private_key, data))


def _now() -> int:
    # LiqPay sends dates as milliseconds since the epoch.
    return int(datetime.now(timezone.utc).timestamp() * 1000)


_client: LiqpayClient | None = None


def get_client() -> LiqpayClient:
    global _client
    if _client is None:
        _client = DemoLiqpayClient() if is_demo() else LiqpayClient(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)
    return _client


def set_client(client) -> None:
    """For tests: swap the provider (e.g. a LiqpayClient with a mock transport)."""
    global _client
    _client = client


# ---------- applying a LiqPay status to an order ----------


def apply_payment(order: Order, payment: dict) -> bool:
    """Updates the order from a LiqPay callback or status answer. Returns
    False when the answer is for another payment attempt or a wrong amount."""
    if payment.get("order_id") != order.payment_reference:
        return False

    status = payment.get("status")
    if status == "sandbox" and not is_sandbox():
        return False  # a test payment never pays for an order in live mode
    if status in PAID_STATUSES or status == "reversed":
        # Never accept a payment for a different amount or currency.
        try:
            amount = Decimal(str(payment.get("amount"))).quantize(Decimal("0.01"))
        except ArithmeticError:
            return False
        if amount != order.payment_amount or payment.get("currency") != CURRENCY:
            return False

    if payment.get("payment_id"):
        order.payment_provider_id = str(payment["payment_id"])

    if status in PAID_STATUSES:
        if order.payment_status != PaymentStatus.REFUNDED:
            order.payment_status = PaymentStatus.PAID
            order.paid_at = order.paid_at or datetime.now(timezone.utc)
    elif status == "reversed":
        order.payment_status = PaymentStatus.REFUNDED
        order.refunded_at = order.refunded_at or datetime.now(timezone.utc)
    elif status in FAILED_STATUSES:
        if order.payment_status not in (PaymentStatus.PAID, PaymentStatus.REFUNDED):
            order.payment_status = PaymentStatus.FAILED
    else:
        # 3ds_verify, processing, wait_secure...: the guest is still paying.
        if order.payment_status not in (PaymentStatus.PAID, PaymentStatus.REFUNDED):
            order.payment_status = PaymentStatus.PENDING
    return True


def handle_callback(session: Session, data: str | None, signature: str | None) -> bool:
    """server_url handler: checks the signature, then applies the status."""
    client = get_client()
    if not data or not signature_ok(client.private_key, data, signature):
        return False
    try:
        payment = decode_data(data)
    except (ValueError, TypeError):
        return False
    order = session.scalar(select(Order).where(Order.payment_reference == payment.get("order_id")))
    if order is None:
        return False
    return apply_payment(order, payment)
