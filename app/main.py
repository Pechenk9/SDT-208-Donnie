from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Branch, BranchProduct, FulfillmentType, Order, OrderItem, OrderStatus, Product
from app.config import get_session
from sqlalchemy.exc import SQLAlchemyError


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
)

@app.get("/store")
def store(
    request: Request,
    session: Session = Depends(get_session),
):
    products = session.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.id)
    ).all()

    return templates.TemplateResponse(
        request,
        "store.html",
        {"products": products},
    )

@app.get("/product/{product_id}")
def product_detail(
    request: Request,
    product_id: int,
    session: Session = Depends(get_session),
):
    product = session.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
        )
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return templates.TemplateResponse(
        request,
        "product.html",
        {"product": product},
    )

@app.get("/order")
def order_page(
    request: Request,
    session: Session = Depends(get_session),
):
    products = session.scalars(
        select(Product).where(Product.is_active.is_(True))
    ).all()

    branches = session.scalars(
        select(Branch).order_by(Branch.city, Branch.name)
    ).all()

    products_data = [
        {
            "id": product.id,
            "name": product.name,
            "base_price": float(product.base_price),
            "image_url": product.image_url,
        }
        for product in products
    ]

    return templates.TemplateResponse(
        request,
        "order.html",
        {
            "branches": branches,
            "products_data": products_data,
        },
    )


@app.post("/orders")
async def create_order(
    request: Request,
    session: Session = Depends(get_session),
):
    try:
        data = await request.json()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    customer_name = data.get("customer_name")
    customer_phone = data.get("customer_phone")
    customer_email = data.get("customer_email")
    branch_id = data.get("branch_id")
    fulfillment_type = data.get("fulfillment_type")
    delivery_address = data.get("delivery_address")
    items = data.get("items")

    if not isinstance(customer_name, str) or not customer_name.strip():
        raise HTTPException(400, "Customer name is required")

    if not isinstance(customer_phone, str) or not customer_phone.strip():
        raise HTTPException(400, "Customer phone is required")

    phone_digits = "".join(
        char for char in customer_phone if char.isdigit()
    )

    if not (
        len(phone_digits) == 10 and phone_digits.startswith("0")
        or len(phone_digits) == 12 and phone_digits.startswith("380")
    ):
        raise HTTPException(400, "Invalid Ukrainian phone number")

    if customer_email is not None:
        if not isinstance(customer_email, str):
            raise HTTPException(400, "Invalid email")

        customer_email = customer_email.strip() or None

        if customer_email and (
            "@" not in customer_email
            or "." not in customer_email.split("@")[-1]
        ):
            raise HTTPException(400, "Invalid email")

    if isinstance(branch_id, bool) or not isinstance(branch_id, int):
        raise HTTPException(400, "Invalid branch")

    try:
        fulfillment_type = FulfillmentType(fulfillment_type)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid fulfillment type")

    if fulfillment_type == FulfillmentType.DELIVERY:
        if not isinstance(delivery_address, str) or not delivery_address.strip():
            raise HTTPException(400, "Delivery address is required")
        delivery_address = delivery_address.strip()
    else:
        delivery_address = None

    if not isinstance(items, list) or not items:
        raise HTTPException(400, "Order must contain at least one item")

    branch = session.get(Branch, branch_id)

    if branch is None:
        raise HTTPException(404, "Branch not found")

    quantities = {}

    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(400, "Invalid order item")

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if (
            isinstance(product_id, bool)
            or not isinstance(product_id, int)
            or product_id <= 0
        ):
            raise HTTPException(400, "Invalid product ID")

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or not 1 <= quantity <= 99
        ):
            raise HTTPException(400, "Invalid product quantity")

        if product_id in quantities:
            raise HTTPException(400, "Duplicate product in order")

        quantities[product_id] = quantity

    products = session.scalars(
        select(Product).where(
            Product.id.in_(quantities.keys()),
            Product.is_active.is_(True),
        )
    ).all()

    products_by_id = {
        product.id: product
        for product in products
    }

    if len(products_by_id) != len(quantities):
        raise HTTPException(
            400,
            "One or more products do not exist or are inactive",
        )

    branch_products = session.scalars(
        select(BranchProduct).where(
            BranchProduct.branch_id == branch_id,
            BranchProduct.product_id.in_(quantities.keys()),
        )
    ).all()

    branch_products_by_id = {
        item.product_id: item
        for item in branch_products
    }

    order_items = []
    total_price = Decimal("0.00")

    for product_id, quantity in quantities.items():
        product = products_by_id[product_id]
        branch_product = branch_products_by_id.get(product_id)

        if branch_product and not branch_product.is_available:
            raise HTTPException(
                400,
                f"{product.name} is unavailable at this branch",
            )

        unit_price = (
            branch_product.price
            if branch_product and branch_product.price is not None
            else product.base_price
        )

        unit_price = Decimal(str(unit_price)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        total_price += unit_price * quantity

        order_items.append(
            OrderItem(
                product_id=product.id,
                name_snapshot=product.name,
                quantity=quantity,
                unit_price=unit_price,
            )
        )

    total_price = total_price.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    order = Order(
        user_id=None,
        branch_id=branch_id,
        status=OrderStatus.PENDING,
        fulfillment_type=fulfillment_type,
        customer_name=customer_name.strip(),
        customer_phone=customer_phone.strip(),
        customer_email=customer_email,
        delivery_address=delivery_address,
        total_price=total_price,
        items=order_items,
    )

    try:
        session.add(order)
        session.commit()
        session.refresh(order)
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create order",
        )

    return {
        "message": "Order created successfully",
        "order_id": order.id,
        "status": order.status.value,
        "total_price": str(order.total_price),
    }
