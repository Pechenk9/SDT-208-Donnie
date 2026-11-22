"""Payment receipts by email.

Two modes, chosen with EMAIL_PROVIDER in .env:

- "console" (default): nothing leaves the computer. Every email is saved as
  an .eml file in OUTBOX_DIR (default: ./outbox) and noted in the log. Open
  the file in any mail app to see the letter exactly as the guest would.
- "smtp": a real mail server, e.g. Gmail with an app password or Mailtrap's
  test inbox. Needs SMTP_HOST; SMTP_USER and SMTP_PASSWORD when the server
  asks for a login. Port 465 uses SSL, any other port uses STARTTLS.

The receipt goes out once per order, after LiqPay confirms the payment:
claim_receipt() marks the order first, so the LiqPay callback and the
guest's return can't both send it. If sending fails, the mark is removed
and the next trigger (for example the guest opening the receipt) retries.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

import certifi
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Order, PaymentStatus
from app.order_extras import KYIV_TZ

log = logging.getLogger("donnie.mail")

PROJECT_DIR = Path(__file__).resolve().parent.parent

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "").strip() or "no-reply@donnie.local"
MAIL_FROM_NAME = "Donnie"
OUTBOX_DIR = Path(os.getenv("OUTBOX_DIR", "").strip() or PROJECT_DIR / "outbox")

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates" / "email"),
    autoescape=select_autoescape(["html"]),
)


def is_console() -> bool:
    return EMAIL_PROVIDER != "smtp" or not SMTP_HOST


def receipt_recipient(order: Order) -> str | None:
    """The address typed at checkout, else the account's email."""
    if order.customer_email:
        return order.customer_email
    if order.user is not None:
        return order.user.email
    return None


# ---------- once per order ----------


def claim_receipt(session: Session, order: Order) -> bool:
    """Marks a paid order's receipt as sent and commits. True only for the
    one request that made the mark, so only that request sends the email."""
    if order.payment_status != PaymentStatus.PAID or not receipt_recipient(order):
        return False
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.payment_status == PaymentStatus.PAID,
            Order.receipt_emailed_at.is_(None),
        )
        .values(receipt_emailed_at=now)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if result.rowcount == 1:
        order.receipt_emailed_at = now
        return True
    return False


def release_receipt(engine: Engine, order_id: int) -> None:
    """Sending failed: remove the mark so a later trigger tries again."""
    with Session(engine) as session:
        session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(receipt_emailed_at=None)
            .execution_options(synchronize_session=False)
        )
        session.commit()


# ---------- the letter ----------


def build_receipt(order: Order, receipt_url: str) -> EmailMessage:
    context = {
        "order": order,
        "receipt_url": receipt_url,
        "money": _money,
        "paid_at": kyiv_time(order.paid_at),
    }
    message = EmailMessage()
    message["Subject"] = f"Donnie: receipt for order #{order.id}"
    message["From"] = formataddr((MAIL_FROM_NAME, MAIL_FROM))
    message["To"] = receipt_recipient(order)
    message["Message-ID"] = make_msgid(domain=MAIL_FROM.split("@")[-1])
    message.set_content(_templates.get_template("receipt.txt").render(context))
    message.add_alternative(
        _templates.get_template("receipt.html").render(context), subtype="html"
    )
    return message


def _money(value) -> str:
    return f"${value:.2f}"


def kyiv_time(moment: datetime | None) -> str | None:
    """'23 Nov 2026, 00:18' in Kyiv time, whatever zone the database used."""
    if moment is None:
        return None
    if moment.tzinfo is None:  # SQLite drops the zone; we always store UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(KYIV_TZ).strftime("%d %b %Y, %H:%M")


# ---------- sending ----------


def _tls_context() -> ssl.SSLContext:
    # certifi's CA list, like httpx uses for LiqPay: a python.org Python on
    # macOS has no system certificates and would fail every TLS check.
    return ssl.create_default_context(cafile=certifi.where())


def send(message: EmailMessage) -> None:
    if is_console():
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        safe_to = re.sub(r"[^A-Za-z0-9@._-]", "_", str(message["To"]))[:80]
        path = OUTBOX_DIR / f"{stamp}-{safe_to}.eml"
        path.write_bytes(bytes(message))
        log.info("Email to %s saved to %s (EMAIL_PROVIDER=console)", message["To"], path)
        return

    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15,
                                  context=_tls_context())
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
    with server:
        if SMTP_PORT != 465:
            server.starttls(context=_tls_context())
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
    log.info("Email to %s sent through %s", message["To"], SMTP_HOST)


def deliver_receipt(message: EmailMessage, engine: Engine, order_id: int) -> None:
    """Runs after the response (FastAPI background task). A mail error never
    touches the payment; it only removes the 'sent' mark for a retry."""
    try:
        send(message)
    except Exception:
        log.exception("Could not email the receipt for order #%s", order_id)
        release_receipt(engine, order_id)
