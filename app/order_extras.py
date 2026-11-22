"""Checkout add-ons and pre-order time slots.

Both ideas come from Kyiv cake shops (Milk Bar, Honey, Baker Street): next to
the order you can add candles, a postcard and gift packaging, and you can pick
a day and a time window instead of "as soon as possible".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.models import (
    CANDLE_PRICE,
    GIFT_BOX_PRICE,
    MAX_CANDLES,
    MAX_POSTCARD_LENGTH,
    MAX_PREORDER_DAYS,
    TIME_SLOTS,
)

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# A slot can be booked for today only if it starts at least this much later,
# so the branch has time to bake and pack the box.
MIN_LEAD_TIME = timedelta(minutes=60)


def kyiv_now() -> datetime:
    return datetime.now(KYIV_TZ)


def slot_start(slot: str) -> time:
    hours, minutes = slot.split("-")[0].split(":")
    return time(int(hours), int(minutes))


def available_slots(day: date, now: datetime | None = None) -> list[str]:
    """Time windows that can still be booked on the given Kyiv-local day."""
    now = now or kyiv_now()
    today = now.date()
    if day < today or day > today + timedelta(days=MAX_PREORDER_DAYS):
        return []
    if day > today:
        return list(TIME_SLOTS)
    earliest = (now + MIN_LEAD_TIME).time()
    return [slot for slot in TIME_SLOTS if slot_start(slot) >= earliest]


def schedule_options(now: datetime | None = None) -> list[dict]:
    """Days (with their bookable windows) for the checkout date picker."""
    now = now or kyiv_now()
    options = []
    for offset in range(MAX_PREORDER_DAYS + 1):
        day = now.date() + timedelta(days=offset)
        slots = available_slots(day, now)
        if slots:
            options.append({"date": day.isoformat(), "slots": slots})
    return options


@dataclass(frozen=True)
class OrderExtras:
    gift_box: bool
    candles: int
    postcard_message: str | None

    @property
    def amount(self) -> Decimal:
        total = Decimal("0.00")
        if self.gift_box:
            total += GIFT_BOX_PRICE
        total += CANDLE_PRICE * self.candles
        return total.quantize(Decimal("0.01"))


def parse_extras(
    gift_box: bool,
    candles: int,
    postcard_message: str | None,
) -> OrderExtras:
    if not 0 <= candles <= MAX_CANDLES:
        raise HTTPException(400, "Invalid number of candles")

    message = (postcard_message or "").strip() or None
    if message is not None:
        # Keep line breaks readable but collapse anything longer.
        message = "\n".join(line.strip() for line in message.splitlines()).strip()
        if len(message) > MAX_POSTCARD_LENGTH:
            raise HTTPException(400, "Postcard message is too long")

    return OrderExtras(
        gift_box=bool(gift_box),
        candles=candles,
        postcard_message=message,
    )


def parse_schedule(
    scheduled_date: str | None,
    time_slot: str | None,
    *,
    is_table_order: bool,
    now: datetime | None = None,
) -> tuple[date | None, str | None]:
    scheduled_date = (scheduled_date or "").strip() or None
    time_slot = (time_slot or "").strip() or None

    if scheduled_date is None and time_slot is None:
        return None, None

    if is_table_order:
        raise HTTPException(400, "Table orders can't be scheduled")

    if scheduled_date is None or time_slot is None:
        raise HTTPException(400, "Choose both a day and a time window")

    try:
        day = date.fromisoformat(scheduled_date)
    except ValueError:
        raise HTTPException(400, "Invalid pre-order date")

    if time_slot not in TIME_SLOTS:
        raise HTTPException(400, "Invalid time window")

    if time_slot not in available_slots(day, now):
        raise HTTPException(400, "This time window is no longer available")

    return day, time_slot


# ---------- order tracker on the receipt ----------

_STATUS_STEP = {
    "pending": 0,
    "confirmed": 1,
    "preparing": 1,
    "ready": 2,
    "completed": 3,
}


def order_progress(order) -> dict | None:
    """Steps for the receipt's order tracker, or None for a cancelled order.

    current is the step the order is at now; when complete is true every
    step, the last one included, is finished.
    """
    status = order.status.value
    if status not in _STATUS_STEP:
        return None

    if order.table_number:
        ready_label, last_label = "Ready", "Served"
    elif order.fulfillment_type.value == "delivery":
        ready_label, last_label = "On the way", "Delivered"
    else:
        ready_label, last_label = "Ready", "Picked up"

    current = _STATUS_STEP[status]
    complete = status == "completed"

    if complete:
        hint = "Enjoy your donuts! Thank you for choosing Donnie."
    elif current == 2:
        if order.table_number:
            hint = f"Your donuts are on their way to table {order.table_number}."
        elif order.fulfillment_type.value == "delivery":
            hint = "The courier is bringing your box."
        else:
            hint = f"Your box is waiting for you at {order.branch.name}."
    elif current == 1:
        hint = "Your donuts are in the oven and getting their glaze."
    elif order.scheduled_date and order.time_slot:
        hint = (
            "We'll bake your box for "
            f"{order.scheduled_date.strftime('%a, %d %b')}, "
            f"{order.time_slot.replace('-', ' – ')}."
        )
    else:
        hint = "We've got your order and will start baking in a moment."

    return {
        "steps": ["Placed", "Baking", ready_label, last_label],
        "current": current,
        "complete": complete,
        "hint": hint,
    }


# ---------- order status changes from the manager panel ----------

_STATUS_FLOW = ("pending", "preparing", "ready", "completed")
STATUS_ACTIONS = ("next", "back", "cancel")


def manager_status_view(order) -> dict:
    """What the manager panel shows for an order: its step name and which
    buttons make sense right now."""
    progress = order_progress(order)
    if progress is None:
        return {"label": "Cancelled", "next": None, "back": False, "cancel": False}

    steps = progress["steps"]
    current = progress["current"]
    complete = progress["complete"]
    return {
        "label": steps[current],
        "next": None if complete else steps[current + 1],
        "back": current > 0,
        "cancel": not complete,
    }


def new_status_after(order, action: str) -> str:
    """Status value an order moves to for a manager action, or HTTP 400."""
    if action not in STATUS_ACTIONS:
        raise HTTPException(400, "Invalid status action")

    status = order.status.value
    if status == "cancelled":
        raise HTTPException(400, "Cancelled orders can't be changed")

    index = _STATUS_STEP[status]
    if action == "next":
        if status == "completed":
            raise HTTPException(400, "This order is already done")
        return _STATUS_FLOW[index + 1]
    if action == "back":
        if index == 0:
            raise HTTPException(400, "This order is already at the first step")
        return _STATUS_FLOW[index - 1]
    if status == "completed":
        raise HTTPException(400, "Completed orders can't be cancelled")
    return "cancelled"
