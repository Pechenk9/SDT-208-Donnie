from decimal import ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import re
from typing import Annotated

from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import (
    COOKIE_NAME,
    COOKIE_SECURE,
    create_login_session,
    get_current_branch,
    get_current_user,
    invalidate_login_session,
    login_required,
)
from app.models import (
    Branch,
    BranchProduct,
    Ingredient,
    FulfillmentType,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductIngredient,
    User,
    UserRole,
)
from app.config import get_session
from app.security import hash_password, verify_password
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


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


def require_profile_user(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )

    return login_required(user)


@app.get("/login")
def login_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse(url="/profile", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "email": ""},
    )


@app.post("/login")
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user is not None:
        return RedirectResponse(url="/profile", status_code=303)

    normalized_email = email.strip().lower()
    account = session.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )

    if account is None or not verify_password(password, account.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Invalid email or password.",
                "email": normalized_email,
            },
            status_code=400,
        )

    invalidate_login_session(request, session)
    response = RedirectResponse(url="/profile", status_code=303)
    create_login_session(account, session, response)
    return response


@app.get("/register")
def registration_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse(url="/profile", status_code=303)

    return templates.TemplateResponse(
        request,
        "register.html",
        {
            "errors": [],
            "first_name": "",
            "last_name": "",
            "email": "",
        },
    )


@app.post("/register")
def register_user(
    request: Request,
    first_name: str = Form(default=""),
    email: str = Form(default=""),
    password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    last_name: str = Form(default=""),
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user is not None:
        return RedirectResponse(url="/profile", status_code=303)

    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip().lower()
    errors = []
    email_is_valid = (
        len(email) <= 255
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None
    )

    if not first_name:
        errors.append("First name is required.")
    elif len(first_name) > 100:
        errors.append("First name must be 100 characters or fewer.")

    if len(last_name) > 100:
        errors.append("Last name must be 100 characters or fewer.")

    if not email:
        errors.append("Email is required.")
    elif not email_is_valid:
        errors.append("Enter a valid email address.")

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")

    if not confirm_password:
        errors.append("Confirm password is required.")
    elif password != confirm_password:
        errors.append("Passwords do not match.")

    if email_is_valid:
        existing_user = session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if existing_user is not None:
            errors.append("An account with this email is already registered.")

    form_values = {
        "errors": errors,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }
    if errors:
        return templates.TemplateResponse(
            request,
            "register.html",
            form_values,
            status_code=400,
        )

    account = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.CUSTOMER,
    )
    session.add(account)

    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "register.html",
            {
                **form_values,
                "errors": ["An account with this email is already registered."],
            },
            status_code=400,
        )

    response = RedirectResponse(url="/profile", status_code=303)
    create_login_session(account, session, response)
    return response


@app.get("/profile")
def profile_page(
    request: Request,
    user: User = Depends(require_profile_user),
):
    return templates.TemplateResponse(
        request,
        "profile.html",
        {"user": user},
    )


@app.post("/logout")
def logout(
    request: Request,
    session: Session = Depends(get_session),
):
    invalidate_login_session(request, session)
    response = RedirectResponse(url="/store", status_code=303)
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response

@app.get("/contacts")
def contacts(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
    )

@app.get("/")
def home(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "home.html",
    )

@app.get("/store")
def store(
    request: Request,
    session: Session = Depends(get_session),
    branch: Branch | None = Depends(get_current_branch),
    user: User | None = Depends(get_current_user),
):
    if branch is None:
        product_rows = [
            (product, None)
            for product in session.scalars(
                select(Product)
                .where(Product.is_active.is_(True))
                .order_by(Product.id)
            ).all()
        ]
    else:
        product_rows = session.execute(
            select(Product, BranchProduct)
            .join(
                BranchProduct,
                and_(
                    BranchProduct.product_id == Product.id,
                    BranchProduct.branch_id == branch.id,
                ),
            )
            .where(Product.is_active.is_(True))
            .order_by(Product.id)
        ).all()

    products = []
    for product, branch_product in product_rows:
        effective_price = (
            branch_product.price
            if branch_product is not None and branch_product.price is not None
            else product.base_price
        )
        products.append(
            {
                "id": product.id,
                "name": product.name,
                "image_url": product.image_url,
                "base_price": float(product.base_price),
                "price": float(effective_price),
                "is_available": (
                    None
                    if branch_product is None
                    else branch_product.is_available
                ),
            }
        )

    selected_branch = (
        {
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
            "city": branch.city,
        }
        if branch is not None
        else None
    )

    return templates.TemplateResponse(
        request,
        "store.html",
        {
            "products": products,
            "selected_branch": selected_branch,
        },
    )

@app.get("/product/{product_id}")
def product_detail(
    request: Request,
    product_id: int,
    session: Session = Depends(get_session),
    branch: Branch | None = Depends(get_current_branch),
    user: User | None = Depends(get_current_user),
):
    product = session.scalar(
        select(Product)
        .options(
            selectinload(Product.branch_availability),
            selectinload(Product.recipe)
            .selectinload(ProductIngredient.ingredient)
            .selectinload(Ingredient.branch_availability),
        )
        .where(
            Product.id == product_id,
            Product.is_active.is_(True),
        )
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    branch_product = next(
        (
            availability
            for availability in product.branch_availability
            if branch is not None and availability.branch_id == branch.id
        ),
        None,
    )
    effective_price = (
        branch_product.price
        if branch_product is not None and branch_product.price is not None
        else product.base_price
    )

    ingredients = []
    for recipe_item in sorted(
        product.recipe,
        key=lambda item: item.ingredient.name.casefold(),
    ):
        ingredient = recipe_item.ingredient
        branch_ingredient = next(
            (
                availability
                for availability in ingredient.branch_availability
                if branch is not None and availability.branch_id == branch.id
            ),
            None,
        )
        branch_is_available = (
            branch_ingredient.is_available
            if branch_ingredient is not None
            else None
        )
        ingredients.append(
            {
                "id": ingredient.id,
                "name": ingredient.name,
                "description": ingredient.description,
                "default_quantity": float(recipe_item.default_quantity),
                "min_quantity": 0,
                "max_quantity": float(recipe_item.max_quantity),
                "is_changeable": recipe_item.is_changeable,
                "unit": recipe_item.unit,
                "extra_price": float(ingredient.extra_price),
                "is_active": ingredient.is_active,
                "branch_is_available": branch_is_available,
                "is_available": (
                    ingredient.is_active
                    and branch_is_available is not False
                ),
            }
        )

    product_data = {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "price": float(effective_price),
        "base_price": float(product.base_price),
        "branch_id": branch.id if branch is not None else None,
        "branch_price": (
            float(branch_product.price)
            if branch_product is not None and branch_product.price is not None
            else None
        ),
        "calories": product.calories,
        "is_active": product.is_active,
        "branch": (
            {
                "id": branch.id,
                "code": branch.code,
                "name": branch.name,
                "city": branch.city,
            }
            if branch is not None
            else None
        ),
        "branch_is_available": (
            branch_product.is_available
            if branch_product is not None
            else None
        ),
        "is_available": (
            None
            if branch is None
            else branch_product is None or branch_product.is_available
        ),
        "ingredients": ingredients,
    }

    return templates.TemplateResponse(
        request,
        "product.html",
        {"product": product_data, "product_data": product_data},
    )

@app.get("/order")
def order_page(
    request: Request,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
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
            "customer": (
                {
                    "name": " ".join(
                        part for part in (user.first_name, user.last_name) if part
                    ),
                    "email": user.email,
                    "phone": user.phone or "",
                }
                if user is not None
                else None
            ),
        },
    )

@app.get("/api/branches")
def list_branches(session: Session = Depends(get_session)):
    branches = session.scalars(
        select(Branch).order_by(Branch.city, Branch.name)
    ).all()

    return [
        {
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
            "city": branch.city,
            "address": branch.address,
        }
        for branch in branches
    ]


@app.get("/orders/{order_id}/receipt")
def order_receipt(
    request: Request,
    order_id: int,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    order = session.scalar(
        select(Order)
        .options(
            joinedload(Order.branch),
            selectinload(Order.items),
        )
        .where(Order.id == order_id)
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return templates.TemplateResponse(
        request,
        "receipt.html",
        {"order": order},
    )


@app.post("/orders")
async def create_order(
    customer_name: Annotated[str, Form(min_length=1)],
    customer_phone: Annotated[str, Form(min_length=1)],
    branch_id: Annotated[int, Form(gt=0)],
    fulfillment_type: Annotated[FulfillmentType, Form()],
    items_json: Annotated[str, Form()],
    customer_email: Annotated[str | None, Form()] = None,
    delivery_address: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
):
    customer_name = customer_name.strip()
    customer_phone = customer_phone.strip()

    if not customer_name:
        raise HTTPException(400, "Customer name is required")

    if not customer_phone:
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
        customer_email = customer_email.strip() or None

        if customer_email and (
            "@" not in customer_email
            or "." not in customer_email.split("@")[-1]
        ):
            raise HTTPException(400, "Invalid email")

    if fulfillment_type == FulfillmentType.DELIVERY:
        if not isinstance(delivery_address, str) or not delivery_address.strip():
            raise HTTPException(400, "Delivery address is required")

        delivery_address = delivery_address.strip()
    else:
        delivery_address = None

    try:
        items = json.loads(items_json)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid order items")

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
        customer_name=customer_name,
        customer_phone=customer_phone,
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

    return RedirectResponse(
        url=f"/orders/{order.id}/receipt",
        status_code=303,
    )
