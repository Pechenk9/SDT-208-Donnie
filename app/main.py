from datetime import datetime, timezone
from decimal import InvalidOperation, ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import re
import secrets
import socket
from typing import Annotated
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import BackgroundTasks, FastAPI, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.routing import Match
from sqlalchemy import and_, delete, func, select
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
    BranchIngredient,
    BranchProduct,
    Ingredient,
    FulfillmentType,
    Order,
    OrderItem,
    OrderItemIngredient,
    OrderStatus,
    IngredientGroup,
    MAX_TABLE_NUMBER,
    CANDLE_PRICE,
    GIFT_BOX_PRICE,
    MAX_CANDLES,
    MAX_POSTCARD_LENGTH,
    PaymentMethod,
    PaymentStatus,
    TIP_PERCENTAGES,
    Product,
    ProductIngredient,
    User,
    UserRole,
    branch_managers,
)
from app.permissions import (
    Permission,
    get_managed_branches,
    has_permission,
    is_owner,
)
from app.config import get_session
from app import liqpay, mailer
from app.product_info import (
    KITCHEN_NOTE,
    STORAGE_NOTE,
    allergens_for,
    bestseller_ids,
    related_products,
)
from app.order_extras import (
    kyiv_now,
    manager_status_view,
    new_status_after,
    order_progress,
    parse_extras,
    parse_schedule,
    schedule_options,
)
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

LANGUAGE_COOKIE = "donnie_language"
SUPPORTED_LANGUAGES = frozenset({"en", "ua"})
_LANGUAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def static_url(path: str) -> str:
    """URL of a static file with its modification time as a version, e.g.
    /static/css/main.css?v=1795106379. When a file changes, the URL changes too,
    so browsers load the new CSS/JS instead of an old cached copy."""
    try:
        version = int((BASE_DIR / "static" / path).stat().st_mtime)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={version}"


templates.env.globals["static_url"] = static_url


def localized(
    value,
    field: str,
    language: str = "en",
    fallback: str | None = None,
) -> str:
    """Return a translated model field, falling back to the other language."""
    alternate_field = f"{field}_en"
    if isinstance(value, dict):
        primary = value.get(alternate_field if language == "en" else field)
        alternate = value.get(field if language == "en" else alternate_field)
    else:
        primary = getattr(value, alternate_field if language == "en" else field, None)
        alternate = getattr(value, field if language == "en" else alternate_field, None)
    return primary or alternate or fallback or ""


templates.env.globals["localized"] = localized

_UKRAINIAN_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")
_UKRAINIAN_MONTHS = (
    "січ", "лют", "бер", "квіт", "трав", "черв",
    "лип", "серп", "вер", "жовт", "лист", "груд",
)
_UKRAINIAN_ENGLISH_MONTHS = dict(
    zip(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        _UKRAINIAN_MONTHS,
    )
)


def short_date(value, language: str) -> str:
    if language != "ua":
        return value.strftime("%a, %d %b")
    return (
        f"{_UKRAINIAN_WEEKDAYS[value.weekday()]}, "
        f"{value.day} {_UKRAINIAN_MONTHS[value.month - 1]}"
    )


def _localized_month_text(text: str | None, language: str) -> str | None:
    if text is None or language != "ua":
        return text
    for english, ukrainian in _UKRAINIAN_ENGLISH_MONTHS.items():
        text = re.sub(rf"\b{english}\b", ukrainian, text)
    return text


templates.env.globals["short_date"] = short_date


def _route_match(path: str, method: str, scope: dict) -> Match:
    candidate_scope = dict(scope)
    candidate_scope["path"] = path
    candidate_scope["raw_path"] = path.encode("utf-8")
    candidate_scope["method"] = method
    best_match = Match.NONE
    for route in app.router.routes:
        match, _ = route.matches(candidate_scope)
        if match == Match.FULL:
            return match
        if match == Match.PARTIAL:
            best_match = match
    return best_match


@app.middleware("http")
async def language_middleware(request: Request, call_next):
    original_path = request.scope["path"]
    explicit_ukrainian = original_path == "/ua" or original_path.startswith("/ua/")
    explicit_english = original_path == "/en" or original_path.startswith("/en/")
    cookie_language = request.cookies.get(LANGUAGE_COOKIE)
    language = (
        "ua" if explicit_ukrainian
        else "en" if explicit_english
        else cookie_language if cookie_language in SUPPORTED_LANGUAGES
        else "en"
    )
    request.state.language = language
    request.state.original_path = original_path
    request.state.current_user = None

    if explicit_ukrainian or explicit_english:
        prefix = "/ua" if explicit_ukrainian else "/en"
        suffix = original_path[len(prefix):] or "/"
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        localized_candidate = f"/en{suffix}"
        candidates = (localized_candidate, suffix)
        destination = next(
            (
                path for path in candidates
                if _route_match(path, request.method, request.scope) == Match.FULL
            ),
            localized_candidate,
        )
        request.scope["path"] = destination
        request.scope["raw_path"] = destination.encode("utf-8")

    response = await call_next(request)
    location = response.headers.get("location")
    if language == "ua" and location:
        parsed_location = urlsplit(location)
        if parsed_location.path == "/en" or parsed_location.path.startswith("/en/"):
            localized_path = f"/ua{parsed_location.path[3:]}"
            response.headers["location"] = urlunsplit(
                parsed_location._replace(path=localized_path)
            )
    response.set_cookie(
        LANGUAGE_COOKIE,
        language,
        max_age=_LANGUAGE_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response


def language_url(request: Request, language: str) -> str:
    """Build the other language's equivalent page URL, retaining its query."""
    original_path = request.state.original_path
    if original_path == "/en" or original_path == "/ua":
        suffix = "/"
    elif original_path.startswith("/en/") or original_path.startswith("/ua/"):
        suffix = original_path[3:]
    else:
        suffix = original_path
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"

    english_path = f"/en{suffix}"
    if (
        _route_match(english_path, "GET", request.scope) != Match.FULL
        or not (BASE_DIR / "templates" / language / _template_for_path(suffix)).is_file()
    ):
        suffix = "/"
    target = f"/{language}{suffix}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return target


def _template_for_path(suffix: str) -> str:
    if suffix in ("/", ""):
        return "home.html"
    if suffix.startswith("/product/"):
        return "product.html"
    if suffix.startswith("/orders/") and suffix.endswith("/receipt"):
        return "receipt.html"
    if suffix.startswith("/orders/") and suffix.endswith("/pay"):
        return "payment.html"
    if suffix.startswith("/demo-liqpay/pay/"):
        return "demo_liqpay.html"
    template_names = {
        "/login": "login.html",
        "/register": "register.html",
        "/profile": "profile.html",
        "/manager": "manager_dashboard.html",
        "/owner": "management_panel.html",
        "/contacts": "contacts.html",
        "/store": "store.html",
        "/order": "order.html",
        "/table": "table.html",
    }
    return template_names.get(suffix, "")


templates.env.globals["language_url"] = language_url


_UKRAINIAN_AUTH_MESSAGES = {
    "Invalid email or password.": "Неправильна електронна пошта або пароль.",
    "First name is required.": "Вкажіть ім’я.",
    "First name must be 100 characters or fewer.": "Ім’я має містити не більше 100 символів.",
    "Last name must be 100 characters or fewer.": "Прізвище має містити не більше 100 символів.",
    "Email is required.": "Вкажіть електронну пошту.",
    "Enter a valid email address.": "Вкажіть дійсну адресу електронної пошти.",
    "Password must be at least 8 characters long.": "Пароль має містити щонайменше 8 символів.",
    "Confirm password is required.": "Підтвердьте пароль.",
    "Passwords do not match.": "Паролі не збігаються.",
    "An account with this email is already registered.": "Обліковий запис із цією адресою вже зареєстровано.",
}


def _localized_auth_message(message: str, language: str) -> str:
    if language == "ua":
        return _UKRAINIAN_AUTH_MESSAGES.get(message, message)
    return message


def _localized_order_hint(progress: dict, order: Order, language: str) -> str:
    if language != "ua":
        return progress["hint"]
    if progress["complete"]:
        return "Смачного! Дякуємо, що обрали Donnie."
    if progress["current"] == 2:
        if order.table_number:
            return f"Ваші пончики вже прямують до столика {order.table_number}."
        if order.fulfillment_type == FulfillmentType.DELIVERY:
            return "Кур’єр везе ваше замовлення."
        branch_name = localized(order.branch, "name", "ua")
        return f"Ваше замовлення чекає на вас у філії {branch_name}."
    if progress["current"] == 1:
        return "Ваші пончики випікаються та вкриваються глазур’ю."
    if order.scheduled_date and order.time_slot:
        date_text = short_date(order.scheduled_date, "ua")
        time_text = order.time_slot.replace("-", " – ")
        return f"Ми приготуємо ваше замовлення {date_text}, {time_text}."
    return "Ми отримали ваше замовлення й скоро почнемо його готувати."


def _render_template(
    request: Request,
    name: str,
    context: dict | None = None,
    **response_options,
):
    language = getattr(request.state, "language", "en")
    template_name = name.split("/", 1)[-1]
    localized_name = f"{language}/{template_name}"
    if not (BASE_DIR / "templates" / localized_name).is_file():
        localized_name = f"en/{template_name}"
    return templates.TemplateResponse(
        request,
        localized_name,
        {**(context or {}), "language": language},
        **response_options,
    )


def _legacy_page_redirect(request: Request, destination: str) -> RedirectResponse:
    query = request.url.query
    if query:
        destination = f"{destination}?{query}"
    return RedirectResponse(url=destination, status_code=307)


@app.get("/")
def root_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/")


@app.get("/login")
def old_login_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/login")


@app.post("/login")
def old_login_post_redirect():
    return RedirectResponse(url="/en/login", status_code=307)


@app.get("/register")
def old_register_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/register")


@app.post("/register")
def old_register_post_redirect():
    return RedirectResponse(url="/en/register", status_code=307)


@app.get("/profile")
def old_profile_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/profile")


@app.get("/manager")
def old_manager_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/manager")


@app.get("/owner")
def old_owner_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/owner")


@app.get("/contacts")
def old_contacts_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/contacts")


@app.get("/store")
def old_store_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/store")


@app.get("/product/{product_id}")
def old_product_redirect(request: Request, product_id: int):
    return _legacy_page_redirect(request, f"/en/product/{product_id}")


@app.get("/order")
def old_order_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/order")


@app.get("/table")
def old_table_redirect(request: Request):
    return _legacy_page_redirect(request, "/en/table")


@app.get("/orders/{order_id}/receipt")
def old_receipt_redirect(request: Request, order_id: int):
    return _legacy_page_redirect(request, f"/en/orders/{order_id}/receipt")


@app.get("/orders/{order_id}/pay")
def old_payment_redirect(request: Request, order_id: int):
    return _legacy_page_redirect(request, f"/en/orders/{order_id}/pay")


@app.get("/demo-liqpay/pay/{reference}")
def old_demo_payment_redirect(request: Request, reference: str):
    return _legacy_page_redirect(request, f"/en/demo-liqpay/pay/{reference}")


# Seasonal donuts shown with a "Limited edition" badge and listed first in the
# catalogue. Matched by product name.
LIMITED_EDITION_PRODUCTS = frozenset({"Neon Sunset"})


def is_limited_edition(product: Product) -> bool:
    return (
        product.name in LIMITED_EDITION_PRODUCTS
        or product.name_en in LIMITED_EDITION_PRODUCTS
    )


def require_profile_user(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/en/login"},
        )

    return login_required(user)


@app.get("/en/login")
def login_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse(url="/en/profile", status_code=303)

    return _render_template(
        request,
        "en/login.html",
        {"error": None, "email": ""},
    )


@app.post("/en/login")
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user is not None:
        return RedirectResponse(url="/en/profile", status_code=303)

    normalized_email = email.strip().lower()
    account = session.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )

    if account is None or not verify_password(password, account.password_hash):
        return _render_template(
            request,
            "en/login.html",
            {
                "error": _localized_auth_message(
                    "Invalid email or password.", request.state.language
                ),
                "email": normalized_email,
            },
            status_code=400,
        )

    invalidate_login_session(request, session)
    response = RedirectResponse(url="/en/profile", status_code=303)
    create_login_session(account, session, response)
    return response


@app.get("/en/register")
def registration_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse(url="/en/profile", status_code=303)

    return _render_template(
        request,
        "en/register.html",
        {
            "errors": [],
            "first_name": "",
            "last_name": "",
            "email": "",
        },
    )


@app.post("/en/register")
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
        return RedirectResponse(url="/en/profile", status_code=303)

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

    errors = [
        _localized_auth_message(message, request.state.language)
        for message in errors
    ]
    form_values = {
        "errors": errors,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }
    if errors:
        return _render_template(
            request,
            "en/register.html",
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
        return _render_template(
            request,
            "en/register.html",
            {
                **form_values,
                "errors": [
                    _localized_auth_message(
                        "An account with this email is already registered.",
                        request.state.language,
                    )
                ],
            },
            status_code=400,
        )

    response = RedirectResponse(url="/en/profile", status_code=303)
    create_login_session(account, session, response)
    return response


@app.get("/en/profile")
def profile_page(
    request: Request,
    user: User = Depends(require_profile_user),
):
    return _render_template(
        request,
        "en/profile.html",
        {
            "user": user,
            "can_access_manager_panel": has_permission(
                user,
                Permission.MANAGER_PANEL,
            ),
            "can_access_owner_panel": has_permission(
                user,
                Permission.OWNER_PANEL,
            ),
        },
    )


_MANAGER_NOTICES = {
    "product-added": "Product added to this branch.",
    "product-updated": "Product availability updated.",
    "product-removed": "Product removed from this branch.",
    "ingredient-added": "Ingredient added to this branch.",
    "ingredient-updated": "Ingredient availability updated.",
    "ingredient-removed": "Ingredient removed from this branch.",
    "order-refunded": "Payment refunded. The order is marked as refunded.",
    "order-status": "Order status updated. The guest sees it on their receipt.",
}

_UKRAINIAN_MANAGER_NOTICES = {
    "product-added": "Товар додано до цієї філії.",
    "product-updated": "Доступність товару оновлено.",
    "product-removed": "Товар вилучено з цієї філії.",
    "ingredient-added": "Інгредієнт додано до цієї філії.",
    "ingredient-updated": "Доступність інгредієнта оновлено.",
    "ingredient-removed": "Інгредієнт вилучено з цієї філії.",
    "order-refunded": "Платіж повернено. Замовлення позначено як повернене.",
    "order-status": "Статус замовлення оновлено.",
}


def _require_manager_branch(
    user: User,
    branch_id: int,
    permission: Permission,
) -> Branch:
    if not has_permission(user, permission):
        raise HTTPException(403, "Manager permission required")

    branch = next(
        (
            branch
            for branch in get_managed_branches(user)
            if branch.id == branch_id
        ),
        None,
    )
    if branch is None:
        raise HTTPException(
            403,
            "You are not assigned to this branch",
        )
    return branch


def _commit_manager_change(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409,
            "The branch association conflicts with existing data",
        )
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(
            500,
            "Could not save branch changes",
        )


def _manager_redirect(branch_id: int, notice_code: str) -> RedirectResponse:
    query = urlencode(
        {
            "branch_id": branch_id,
            "notice": notice_code,
        }
    )
    return RedirectResponse(
        url=f"/en/manager?{query}",
        status_code=303,
    )


@app.get("/en/manager")
def manager_panel(
    request: Request,
    branch_id: int | None = None,
    notice: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    if not has_permission(user, Permission.MANAGER_PANEL):
        raise HTTPException(403, "Manager panel access required")

    managed_branches = get_managed_branches(user)
    if not managed_branches:
        raise HTTPException(403, "No branches are assigned to this manager")

    if branch_id is None:
        selected_branch = managed_branches[0]
    else:
        selected_branch = _require_manager_branch(
            user,
            branch_id,
            Permission.MANAGER_PANEL,
        )

    product_rows = session.execute(
        select(BranchProduct, Product)
        .join(Product, Product.id == BranchProduct.product_id)
        .where(BranchProduct.branch_id == selected_branch.id)
        .order_by(Product.name)
    ).all()
    branch_products = [
        {"association": association, "product": product}
        for association, product in product_rows
    ]
    associated_product_ids = {
        association.product_id
        for association, _ in product_rows
    }
    catalogue_products = session.scalars(
        select(Product)
        .where(~Product.id.in_(associated_product_ids))
        .order_by(Product.name)
    ).all()

    ingredient_rows = session.execute(
        select(BranchIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == BranchIngredient.ingredient_id)
        .where(BranchIngredient.branch_id == selected_branch.id)
        .order_by(Ingredient.name)
    ).all()
    branch_ingredients = [
        {"association": association, "ingredient": ingredient}
        for association, ingredient in ingredient_rows
    ]
    associated_ingredient_ids = {
        association.ingredient_id
        for association, _ in ingredient_rows
    }
    catalogue_ingredients = session.scalars(
        select(Ingredient)
        .where(~Ingredient.id.in_(associated_ingredient_ids))
        .order_by(Ingredient.name)
    ).all()

    recent_orders = session.scalars(
        select(Order)
        .where(Order.branch_id == selected_branch.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(20)
    ).all()

    return _render_template(
        request,
        "en/manager_dashboard.html",
        {
            "recent_orders": recent_orders,
            "order_status_views": {
                order.id: manager_status_view(order) for order in recent_orders
            },
            "qr_base_url": _phone_base(request),
            "managed_branches": managed_branches,
            "selected_branch": selected_branch,
            "branch_products": branch_products,
            "catalogue_products": catalogue_products,
            "branch_ingredients": branch_ingredients,
            "catalogue_ingredients": catalogue_ingredients,
            "notice": (
                _UKRAINIAN_MANAGER_NOTICES.get(notice)
                if request.state.language == "ua"
                else _MANAGER_NOTICES.get(notice)
            ),
        },
    )


@app.post("/manager/products/add")
def add_branch_product(
    branch_id: Annotated[int, Form(gt=0)],
    product_id: Annotated[int, Form(gt=0)],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_PRODUCT_AVAILABILITY,
    )
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")

    association = session.get(BranchProduct, (branch.id, product.id))
    if association is not None:
        raise HTTPException(409, "Product is already associated with this branch")

    session.add(
        BranchProduct(
            branch_id=branch.id,
            product_id=product.id,
            is_available=True,
            price=None,
        )
    )
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "product-added")


@app.post("/manager/products/{product_id}/availability")
def update_branch_product_availability(
    product_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    is_available: Annotated[bool, Form()],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_PRODUCT_AVAILABILITY,
    )
    association = session.scalar(
        select(BranchProduct).where(
            BranchProduct.branch_id == branch.id,
            BranchProduct.product_id == product_id,
        )
    )
    if association is None:
        raise HTTPException(404, "Product association not found")

    association.is_available = is_available
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "product-updated")


@app.post("/manager/products/{product_id}/remove")
def remove_branch_product(
    product_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_PRODUCT_AVAILABILITY,
    )
    association = session.scalar(
        select(BranchProduct).where(
            BranchProduct.branch_id == branch.id,
            BranchProduct.product_id == product_id,
        )
    )
    if association is None:
        raise HTTPException(404, "Product association not found")

    session.delete(association)
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "product-removed")


@app.post("/manager/ingredients/add")
def add_branch_ingredient(
    branch_id: Annotated[int, Form(gt=0)],
    ingredient_id: Annotated[int, Form(gt=0)],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_INGREDIENT_AVAILABILITY,
    )
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(404, "Ingredient not found")

    association = session.get(
        BranchIngredient,
        (branch.id, ingredient.id),
    )
    if association is not None:
        raise HTTPException(
            409,
            "Ingredient is already associated with this branch",
        )

    session.add(
        BranchIngredient(
            branch_id=branch.id,
            ingredient_id=ingredient.id,
            is_available=True,
        )
    )
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "ingredient-added")


@app.post("/manager/ingredients/{ingredient_id}/availability")
def update_branch_ingredient_availability(
    ingredient_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    is_available: Annotated[bool, Form()],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_INGREDIENT_AVAILABILITY,
    )
    association = session.scalar(
        select(BranchIngredient).where(
            BranchIngredient.branch_id == branch.id,
            BranchIngredient.ingredient_id == ingredient_id,
        )
    )
    if association is None:
        raise HTTPException(404, "Ingredient association not found")

    association.is_available = is_available
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "ingredient-updated")


@app.post("/manager/ingredients/{ingredient_id}/remove")
def remove_branch_ingredient(
    ingredient_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(
        user,
        branch_id,
        Permission.UPDATE_INGREDIENT_AVAILABILITY,
    )
    association = session.scalar(
        select(BranchIngredient).where(
            BranchIngredient.branch_id == branch.id,
            BranchIngredient.ingredient_id == ingredient_id,
        )
    )
    if association is None:
        raise HTTPException(404, "Ingredient association not found")

    session.delete(association)
    _commit_manager_change(session)
    return _manager_redirect(branch.id, "ingredient-removed")


_OWNER_NOTICES = {
    "manager-assigned": "Manager assigned to the branch.",
    "manager-removed": "Manager assignment removed.",
    "product-created": "Product added to the global catalogue.",
    "product-updated": "Global product details updated.",
    "ingredient-created": "Ingredient added to the global catalogue.",
    "ingredient-updated": "Global ingredient details updated.",
}

_OWNER_ERRORS = {
    "invalid-form": "Check the form values and try again.",
    "duplicate": "A catalogue item with that name already exists.",
    "not-found": "The requested record was not found.",
    "invalid-assignment": "Select an existing customer or manager and branch.",
    "already-assigned": "This user is already assigned to that branch.",
    "assignment-not-found": "That manager is not assigned to this branch.",
    "group-not-found": "Select an existing ingredient group.",
    "conflict": "The change conflicts with existing data and was not saved.",
    "save-failed": "The change could not be saved. Please try again.",
}

_UKRAINIAN_OWNER_NOTICES = {
    "manager-assigned": "Менеджера призначено до філії.",
    "manager-removed": "Призначення менеджера скасовано.",
    "product-created": "Товар додано до загального каталогу.",
    "product-updated": "Дані товару в загальному каталозі оновлено.",
    "ingredient-created": "Інгредієнт додано до загального каталогу.",
    "ingredient-updated": "Дані інгредієнта в загальному каталозі оновлено.",
}

_UKRAINIAN_OWNER_ERRORS = {
    "invalid-form": "Перевірте поля форми та спробуйте ще раз.",
    "duplicate": "Елемент каталогу з такою назвою вже існує.",
    "not-found": "Запис не знайдено.",
    "invalid-assignment": "Виберіть наявного клієнта або менеджера та філію.",
    "already-assigned": "Цього користувача вже призначено до цієї філії.",
    "assignment-not-found": "Цього менеджера не призначено до цієї філії.",
    "group-not-found": "Виберіть наявну групу інгредієнтів.",
    "conflict": "Зміна конфліктує з наявними даними й не була збережена.",
    "save-failed": "Не вдалося зберегти зміни. Спробуйте ще раз.",
}


def _require_owner(user: User) -> None:
    if not is_owner(user) or not has_permission(user, Permission.OWNER_PANEL):
        raise HTTPException(403, "Owner panel access required")


def _owner_redirect(
    section: str,
    *,
    notice: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    query = {}
    if notice is not None:
        query["notice"] = notice
    if error is not None:
        query["error"] = error
    url = "/owner"
    if query:
        url += f"?{urlencode(query)}"
    return RedirectResponse(
        url=f"{url}#{section}",
        status_code=303,
    )


def _commit_owner_change(
    session: Session,
    section: str,
    notice: str,
) -> RedirectResponse:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _owner_redirect(section, error="conflict")
    except SQLAlchemyError:
        session.rollback()
        return _owner_redirect(section, error="save-failed")
    return _owner_redirect(section, notice=notice)


def _parse_owner_id(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_owner_money(value: str) -> Decimal | None:
    try:
        amount = Decimal(value.strip())
    except (AttributeError, InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99"):
        return None
    try:
        rounded_amount = amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if amount != rounded_amount:
        return None
    return amount


def _product_form_values(
    name: str,
    description: str,
    base_price: str,
    calories: str,
    image_url: str,
    is_active: bool,
    name_en: str | None = None,
    description_en: str | None = None,
) -> dict | None:
    name = name.strip()
    if name_en is not None:
        name_en = name_en.strip()
    price = _parse_owner_money(base_price)
    calories_text = calories.strip()
    parsed_calories = None
    if calories_text:
        try:
            parsed_calories = int(calories_text)
        except ValueError:
            return None
        if not 0 <= parsed_calories <= 2147483647:
            return None

    if (
        not name
        or len(name) > 150
        or (name_en is not None and len(name_en) > 150)
        or price is None
    ):
        return None

    values = {
        "name": name,
        "description": description.strip() or None,
        "base_price": price,
        "calories": parsed_calories,
        "image_url": image_url.strip() or None,
        "is_active": is_active,
    }
    if name_en is not None:
        values["name_en"] = name_en or None
    if description_en is not None:
        values["description_en"] = description_en.strip() or None
    return values


def _ingredient_form_values(
    name: str,
    description: str,
    extra_price: str,
    group_id: str,
    is_active: bool,
    name_en: str | None = None,
    description_en: str | None = None,
) -> tuple[dict | None, int | None]:
    name = name.strip()
    if name_en is not None:
        name_en = name_en.strip()
    price = _parse_owner_money(extra_price)
    parsed_group_id = _parse_owner_id(group_id)
    if (
        not name
        or len(name) > 150
        or (name_en is not None and len(name_en) > 150)
        or price is None
        or parsed_group_id is None
    ):
        return None, None

    values = {
        "name": name,
        "description": description.strip() or None,
        "extra_price": price,
        "group_id": parsed_group_id,
        "is_active": is_active,
    }
    if name_en is not None:
        values["name_en"] = name_en or None
    if description_en is not None:
        values["description_en"] = description_en.strip() or None
    return values, parsed_group_id


@app.get("/en/owner")
def owner_panel(
    request: Request,
    notice: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)

    branches = session.scalars(
        select(Branch)
        .options(selectinload(Branch.managers))
        .order_by(Branch.city, Branch.name, Branch.id)
    ).all()
    owner_users = session.scalars(
        select(User)
        .where(User.role.in_((UserRole.CUSTOMER, UserRole.MANAGER)))
        .options(selectinload(User.managed_branches))
        .order_by(User.last_name, User.first_name, User.id)
    ).all()
    managers = [
        account for account in owner_users
        if account.role == UserRole.MANAGER
    ]
    staff_branches = []
    for branch in branches:
        branch_managers_list = [
            manager
            for manager in branch.managers
            if manager.role == UserRole.MANAGER
        ]
        assigned_ids = {manager.id for manager in branch_managers_list}
        staff_branches.append(
            {
                "branch": branch,
                "managers": branch_managers_list,
                "available_users": [
                    account
                    for account in owner_users
                    if account.id not in assigned_ids
                ],
            }
        )
    products = session.scalars(
        select(Product).order_by(Product.name, Product.id)
    ).all()
    ingredient_groups = session.scalars(
        select(IngredientGroup).order_by(IngredientGroup.name)
    ).all()
    ingredients = session.scalars(
        select(Ingredient)
        .options(joinedload(Ingredient.group))
        .order_by(Ingredient.name, Ingredient.id)
    ).all()

    return _render_template(
        request,
        "en/management_panel.html",
        {
            "user": user,
            "staff_branches": staff_branches,
            "owner_users": owner_users,
            "managers": managers,
            "products": products,
            "ingredients": ingredients,
            "ingredient_groups": ingredient_groups,
            "notice": (
                _UKRAINIAN_OWNER_NOTICES.get(notice)
                if request.state.language == "ua"
                else _OWNER_NOTICES.get(notice)
            ),
            "error": (
                _UKRAINIAN_OWNER_ERRORS.get(error)
                if request.state.language == "ua"
                else _OWNER_ERRORS.get(error)
            ),
        },
    )


@app.post("/owner/staff/assign")
def owner_assign_manager(
    branch_id: str = Form(default=""),
    user_id: str = Form(default=""),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    parsed_branch_id = _parse_owner_id(branch_id)
    parsed_user_id = _parse_owner_id(user_id)
    if parsed_branch_id is None or parsed_user_id is None:
        return _owner_redirect("staff", error="invalid-assignment")

    branch = session.get(Branch, parsed_branch_id)
    account = session.get(User, parsed_user_id)
    if (
        branch is None
        or account is None
        or account.role not in (UserRole.CUSTOMER, UserRole.MANAGER)
    ):
        return _owner_redirect("staff", error="invalid-assignment")

    assignment = session.execute(
        select(branch_managers.c.user_id).where(
            branch_managers.c.user_id == account.id,
            branch_managers.c.branch_id == branch.id,
        )
    ).first()
    if assignment is not None:
        return _owner_redirect("staff", error="already-assigned")

    account.role = UserRole.MANAGER
    branch.managers.append(account)
    return _commit_owner_change(session, "staff", "manager-assigned")


@app.post("/owner/staff/remove")
def owner_remove_manager(
    branch_id: str = Form(default=""),
    user_id: str = Form(default=""),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    parsed_branch_id = _parse_owner_id(branch_id)
    parsed_user_id = _parse_owner_id(user_id)
    if parsed_branch_id is None or parsed_user_id is None:
        return _owner_redirect("staff", error="invalid-assignment")

    branch = session.get(Branch, parsed_branch_id)
    account = session.get(User, parsed_user_id)
    if (
        branch is None
        or account is None
        or account.role != UserRole.MANAGER
    ):
        return _owner_redirect("staff", error="assignment-not-found")

    result = session.execute(
        delete(branch_managers).where(
            branch_managers.c.user_id == account.id,
            branch_managers.c.branch_id == branch.id,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        return _owner_redirect("staff", error="assignment-not-found")

    remaining_assignments = session.scalar(
        select(func.count())
        .select_from(branch_managers)
        .where(branch_managers.c.user_id == account.id)
    )
    if remaining_assignments == 0:
        account.role = UserRole.CUSTOMER

    return _commit_owner_change(session, "staff", "manager-removed")


@app.post("/owner/products/create")
def owner_create_product(
    name: str = Form(default=""),
    description: str = Form(default=""),
    name_en: str | None = Form(default=None),
    description_en: str | None = Form(default=None),
    base_price: str = Form(default=""),
    calories: str = Form(default=""),
    image_url: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    values = _product_form_values(
        name, description, base_price, calories, image_url, is_active,
        name_en, description_en,
    )
    if values is None:
        return _owner_redirect("products", error="invalid-form")

    duplicate = session.scalar(
        select(Product.id).where(func.lower(Product.name) == values["name"].lower())
    )
    if duplicate is None and values.get("name_en"):
        duplicate = session.scalar(
            select(Product.id).where(
                func.lower(Product.name_en) == values["name_en"].lower()
            )
        )
    if duplicate is not None:
        return _owner_redirect("products", error="duplicate")

    session.add(Product(**values))
    return _commit_owner_change(session, "products", "product-created")


@app.post("/owner/products/{product_id}/edit")
def owner_edit_product(
    product_id: int,
    name: str = Form(default=""),
    description: str = Form(default=""),
    name_en: str | None = Form(default=None),
    description_en: str | None = Form(default=None),
    base_price: str = Form(default=""),
    calories: str = Form(default=""),
    image_url: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    product = session.get(Product, product_id)
    if product is None:
        return _owner_redirect("products", error="not-found")

    values = _product_form_values(
        name, description, base_price, calories, image_url, is_active,
        name_en, description_en,
    )
    if values is None:
        return _owner_redirect("products", error="invalid-form")

    duplicate = session.scalar(
        select(Product.id).where(
            func.lower(Product.name) == values["name"].lower(),
            Product.id != product.id,
        )
    )
    if duplicate is None and values.get("name_en"):
        duplicate = session.scalar(
            select(Product.id).where(
                func.lower(Product.name_en) == values["name_en"].lower(),
                Product.id != product.id,
            )
        )
    if duplicate is not None:
        return _owner_redirect("products", error="duplicate")

    for field, value in values.items():
        setattr(product, field, value)
    return _commit_owner_change(session, "products", "product-updated")


@app.post("/owner/ingredients/create")
def owner_create_ingredient(
    name: str = Form(default=""),
    description: str = Form(default=""),
    name_en: str | None = Form(default=None),
    description_en: str | None = Form(default=None),
    extra_price: str = Form(default=""),
    group_id: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    values, parsed_group_id = _ingredient_form_values(
        name, description, extra_price, group_id, is_active,
        name_en, description_en,
    )
    if values is None or parsed_group_id is None:
        return _owner_redirect("ingredients", error="invalid-form")

    group = session.get(IngredientGroup, parsed_group_id)
    if group is None:
        return _owner_redirect("ingredients", error="group-not-found")

    duplicate = session.scalar(
        select(Ingredient.id).where(
            func.lower(Ingredient.name) == values["name"].lower()
        )
    )
    if duplicate is None and values.get("name_en"):
        duplicate = session.scalar(
            select(Ingredient.id).where(
                func.lower(Ingredient.name_en) == values["name_en"].lower()
            )
        )
    if duplicate is not None:
        return _owner_redirect("ingredients", error="duplicate")

    session.add(Ingredient(**values))
    return _commit_owner_change(session, "ingredients", "ingredient-created")


@app.post("/owner/ingredients/{ingredient_id}/edit")
def owner_edit_ingredient(
    ingredient_id: int,
    name: str = Form(default=""),
    description: str = Form(default=""),
    name_en: str | None = Form(default=None),
    description_en: str | None = Form(default=None),
    extra_price: str = Form(default=""),
    group_id: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None:
        return _owner_redirect("ingredients", error="not-found")

    values, parsed_group_id = _ingredient_form_values(
        name, description, extra_price, group_id, is_active,
        name_en, description_en,
    )
    if values is None or parsed_group_id is None:
        return _owner_redirect("ingredients", error="invalid-form")

    group = session.get(IngredientGroup, parsed_group_id)
    if group is None:
        return _owner_redirect("ingredients", error="group-not-found")

    duplicate = session.scalar(
        select(Ingredient.id).where(
            func.lower(Ingredient.name) == values["name"].lower(),
            Ingredient.id != ingredient.id,
        )
    )
    if duplicate is None and values.get("name_en"):
        duplicate = session.scalar(
            select(Ingredient.id).where(
                func.lower(Ingredient.name_en) == values["name_en"].lower(),
                Ingredient.id != ingredient.id,
            )
        )
    if duplicate is not None:
        return _owner_redirect("ingredients", error="duplicate")

    for field, value in values.items():
        setattr(ingredient, field, value)
    return _commit_owner_change(session, "ingredients", "ingredient-updated")


@app.post("/logout")
def logout(
    request: Request,
    session: Session = Depends(get_session),
):
    invalidate_login_session(request, session)
    response = RedirectResponse(url="/en/store", status_code=303)
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response

@app.get("/en/contacts")
def contacts(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    return _render_template(
        request=request,
        name="en/contacts.html",
    )

@app.get("/en/")
def home(
    request: Request,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    featured = session.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.id)
        .limit(4)
    ).all()
    branches = session.scalars(
        select(Branch).order_by(Branch.city, Branch.name)
    ).all()
    seasonal = session.scalars(
        select(Product)
        .where(
            Product.is_active.is_(True),
            (
                Product.name.in_(LIMITED_EDITION_PRODUCTS)
                | Product.name_en.in_(LIMITED_EDITION_PRODUCTS)
            ),
        )
        .order_by(Product.id)
    ).all()

    return _render_template(
        request,
        "en/home.html",
        {
            "featured": featured,
            "branches": branches,
            "seasonal": seasonal,
            "bestsellers": bestseller_ids(session),
        },
    )

@app.get("/en/store")
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

    bestsellers = bestseller_ids(session)
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
                "name": localized(product, "name", request.state.language),
                "description": localized(
                    product, "description", request.state.language
                ),
                "image_url": product.image_url,
                "is_limited": is_limited_edition(product),
                "is_bestseller": product.id in bestsellers,
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
            "name": localized(branch, "name", request.state.language),
            "city": localized(branch, "city", request.state.language),
        }
        if branch is not None
        else None
    )

    return _render_template(
        request,
        "en/store.html",
        {
            "products": products,
            "selected_branch": selected_branch,
        },
    )

@app.get("/en/product/{product_id}")
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
                "name": localized(ingredient, "name", request.state.language),
                "description": localized(
                    ingredient, "description", request.state.language
                ),
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

    allergens = allergens_for(
        name
        for recipe_item in product.recipe
        if recipe_item.default_quantity > 0
        for name in (
            recipe_item.ingredient.name,
            recipe_item.ingredient.name_en or "",
        )
    )

    if branch is not None:
        branch_offers = {
            offer.product_id: offer
            for offer in session.scalars(
                select(BranchProduct).where(
                    BranchProduct.branch_id == branch.id,
                    BranchProduct.is_available.is_(True),
                )
            ).all()
        }
        related = related_products(
            session,
            product,
            allowed_ids=set(branch_offers),
        )
    else:
        branch_offers = {}
        related = related_products(session, product)

    related_data = [
        {
            "id": item.id,
            "name": localized(item, "name", request.state.language),
            "image_url": item.image_url,
            "is_limited": is_limited_edition(item),
            "price": float(
                branch_offers[item.id].price
                if item.id in branch_offers
                and branch_offers[item.id].price is not None
                else item.base_price
            ),
        }
        for item in related
    ]

    product_data = {
        "id": product.id,
        "name": localized(product, "name", request.state.language),
        "description": localized(product, "description", request.state.language),
        "image_url": product.image_url,
        "is_limited": is_limited_edition(product),
        "is_bestseller": product.id in bestseller_ids(session),
        "allergens": allergens,
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
                "name": localized(branch, "name", request.state.language),
                "city": localized(branch, "city", request.state.language),
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
            else branch_product is not None and branch_product.is_available
        ),
        "ingredients": ingredients,
    }

    return _render_template(
        request,
        "en/product.html",
        {
            "product": product_data,
            "product_data": product_data,
            "related": related_data,
            "storage_note": (
                "Найкраще смакує в день випікання. Зберігайте до 24 годин у "
                "холодильнику за температури +2…+6 °C. Щоб повернути м’якість, "
                "підігрійте 10 секунд у мікрохвильовці."
                if request.state.language == "ua"
                else STORAGE_NOTE
            ),
            "kitchen_note": (
                "Усі пончики готуються на одній кухні, де також працюють із горіхами, "
                "глютеном, молоком, яйцями та соєю, тому можливі їхні сліди."
                if request.state.language == "ua"
                else KITCHEN_NOTE
            ),
        },
    )

@app.get("/en/order")
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
            "name": localized(product, "name", request.state.language),
            "base_price": float(product.base_price),
            "image_url": product.image_url,
        }
        for product in products
    ]

    return _render_template(
        request,
        "en/order.html",
        {
            "branches": branches,
            "products_data": products_data,
            "extras_config": {
                "gift_box_price": float(GIFT_BOX_PRICE),
                "candle_price": float(CANDLE_PRICE),
                "max_candles": MAX_CANDLES,
                "max_postcard_length": MAX_POSTCARD_LENGTH,
                "schedule": schedule_options(),
                "today": kyiv_now().date().isoformat(),
            },
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
def list_branches(
    request: Request,
    session: Session = Depends(get_session),
):
    branches = session.scalars(
        select(Branch).order_by(Branch.city, Branch.name)
    ).all()

    return [
        {
            "id": branch.id,
            "code": branch.code,
            "name": localized(branch, "name", request.state.language),
            "city": localized(branch, "city", request.state.language),
            "address": localized(branch, "address", request.state.language),
        }
        for branch in branches
    ]


@app.get("/en/orders/{order_id}/receipt")
def order_receipt(
    request: Request,
    order_id: int,
    background_tasks: BackgroundTasks,
    paid: bool = False,
    scan: bool = False,
    t: str | None = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    order = session.scalar(
        select(Order)
        .options(
            joinedload(Order.branch),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
        .where(Order.id == order_id)
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )
    _require_order_access(request, order, user, t)

    # Retries a receipt email that failed earlier (no-op once it was sent).
    _queue_receipt_email(background_tasks, session, order, request)
    progress = order_progress(order)
    if progress is not None:
        progress = {
            **progress,
            "hint": _localized_order_hint(
                progress, order, request.state.language
            ),
        }

    response = _render_template(
        request,
        "en/receipt.html",
        {
            "order": order,
            # Opened by scanning the ticket's QR: lead with whether it's paid.
            "scanned": scan,
            "paid_at_text": _localized_month_text(
                mailer.kyiv_time(order.paid_at), request.state.language
            ),
            "just_paid": not scan and paid and order.payment_status == PaymentStatus.PAID,
            "progress": progress,
            "qr_url": (
                f"{_phone_base(request)}/{request.state.language}"
                f"/orders/{order.id}/receipt"
                f"?t={order.access_token}&scan=1"
            ),
        },
    )
    if _token_ok(order, t):
        # Opened from the emailed link: this browser may now poll the status.
        _remember_order(response, order)
    return response


@app.post("/orders")
async def create_order(
    customer_name: Annotated[str, Form(min_length=1)],
    customer_phone: Annotated[str, Form(min_length=1)],
    branch_id: Annotated[int, Form(gt=0)],
    fulfillment_type: Annotated[FulfillmentType, Form()],
    items_json: Annotated[str, Form()],
    customer_email: Annotated[str | None, Form()] = None,
    delivery_address: Annotated[str | None, Form()] = None,
    tip_percent: Annotated[int, Form()] = 0,
    payment_method: Annotated[str, Form()] = PaymentMethod.ON_RECEIPT,
    table_number: Annotated[int | None, Form()] = None,
    gift_box: Annotated[bool, Form()] = False,
    candles: Annotated[int, Form()] = 0,
    postcard_message: Annotated[str | None, Form()] = None,
    scheduled_date: Annotated[str | None, Form()] = None,
    time_slot: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if tip_percent not in TIP_PERCENTAGES:
        raise HTTPException(400, "Invalid tip")

    extras = parse_extras(gift_box, candles, postcard_message)
    scheduled_day, time_slot = parse_schedule(
        scheduled_date,
        time_slot,
        is_table_order=table_number is not None,
    )

    if payment_method not in PaymentMethod.ALL:
        raise HTTPException(400, "Invalid payment method")

    if table_number is not None:
        if fulfillment_type != FulfillmentType.PICKUP:
            raise HTTPException(400, "Table orders can't be delivered")
        if not 1 <= table_number <= MAX_TABLE_NUMBER:
            raise HTTPException(400, "Invalid table number")

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

    product_ids = set()
    total_quantity = 0
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(400, "Invalid order item")

        product_id = item.get("product_id")
        quantity = item.get("quantity")
        ingredients = item.get("ingredients")
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
        if not isinstance(ingredients, list):
            raise HTTPException(400, "Invalid ingredient selections")

        item["product_id"] = product_id
        item["quantity"] = quantity
        product_ids.add(product_id)
        total_quantity += quantity

    if total_quantity < 6:
        raise HTTPException(400, "Order must contain at least six donuts")

    try:
        branch = session.get(Branch, branch_id)
        if branch is None:
            raise HTTPException(404, "Branch not found")

        products = session.scalars(
            select(Product).where(
                Product.id.in_(product_ids),
                Product.is_active.is_(True),
            )
        ).all()
        products_by_id = {product.id: product for product in products}
        if len(products_by_id) != len(product_ids):
            raise HTTPException(
                400,
                "One or more products do not exist or are inactive",
            )

        branch_products = session.scalars(
            select(BranchProduct).where(
                BranchProduct.branch_id == branch_id,
                BranchProduct.product_id.in_(product_ids),
            )
        ).all()
        branch_products_by_id = {
            availability.product_id: availability
            for availability in branch_products
        }

        recipes = session.scalars(
            select(ProductIngredient)
            .options(joinedload(ProductIngredient.ingredient))
            .where(ProductIngredient.product_id.in_(product_ids))
        ).all()
        recipes_by_product = {}
        for recipe in recipes:
            recipes_by_product.setdefault(recipe.product_id, {})[
                recipe.ingredient_id
            ] = recipe

        submitted_ingredient_ids = set()
        for item in items:
            seen_ingredient_ids = set()
            for selection in item["ingredients"]:
                if not isinstance(selection, dict):
                    raise HTTPException(400, "Invalid ingredient selection")
                ingredient_id = selection.get("ingredient_id")
                quantity = selection.get("quantity")
                if (
                    isinstance(ingredient_id, bool)
                    or not isinstance(ingredient_id, int)
                    or ingredient_id <= 0
                ):
                    raise HTTPException(400, "Invalid ingredient ID")
                if ingredient_id in seen_ingredient_ids:
                    raise HTTPException(
                        400,
                        "Duplicate ingredient in order item",
                    )
                seen_ingredient_ids.add(ingredient_id)
                try:
                    parsed_quantity = (
                        Decimal(str(quantity))
                        if not isinstance(quantity, bool)
                        and isinstance(quantity, (int, float))
                        else Decimal("NaN")
                    )
                except (InvalidOperation, ValueError):
                    parsed_quantity = Decimal("NaN")
                try:
                    valid_quantity = (
                        parsed_quantity.is_finite()
                        and parsed_quantity >= 0
                        and parsed_quantity
                        == parsed_quantity.quantize(Decimal("0.001"))
                    )
                except InvalidOperation:
                    valid_quantity = False
                if not valid_quantity:
                    raise HTTPException(400, "Invalid ingredient quantity")
                selection["ingredient_id"] = ingredient_id
                selection["quantity"] = parsed_quantity
                submitted_ingredient_ids.add(ingredient_id)

        branch_ingredients = session.scalars(
            select(BranchIngredient).where(
                BranchIngredient.branch_id == branch_id,
                BranchIngredient.ingredient_id.in_(submitted_ingredient_ids),
            )
        ).all() if submitted_ingredient_ids else []
        branch_ingredients_by_id = {
            availability.ingredient_id: availability
            for availability in branch_ingredients
        }

        order_items = []
        total_price = Decimal("0.00")
        for item in items:
            product = products_by_id[item["product_id"]]
            branch_product = branch_products_by_id.get(product.id)
            if branch_product is None or not branch_product.is_available:
                raise HTTPException(
                    400,
                    f"{product.name} is unavailable at this branch",
                )

            recipes_for_product = recipes_by_product.get(product.id, {})
            surcharge = Decimal("0.00")
            ingredient_records = []
            for selection in item["ingredients"]:
                recipe = recipes_for_product.get(selection["ingredient_id"])
                if recipe is None:
                    raise HTTPException(
                        400,
                        "Ingredient does not belong to this product",
                    )

                quantity = selection["quantity"]
                if quantity > recipe.max_quantity:
                    raise HTTPException(
                        400,
                        f"{recipe.ingredient.name} exceeds its maximum quantity",
                    )
                if not recipe.is_changeable and quantity != recipe.default_quantity:
                    raise HTTPException(
                        400,
                        f"{recipe.ingredient.name} cannot be customised",
                    )

                availability = branch_ingredients_by_id.get(
                    recipe.ingredient_id
                )
                is_available = (
                    recipe.ingredient.is_active
                    and (
                        availability is None
                        or availability.is_available
                    )
                )
                if quantity > 0 and not is_available:
                    raise HTTPException(
                        400,
                        f"{recipe.ingredient.name} is unavailable at this branch",
                    )
                if (
                    recipe.is_changeable
                    and quantity > recipe.default_quantity
                ):
                    surcharge += recipe.ingredient.extra_price
                if quantity > 0:
                    ingredient_records.append(
                        OrderItemIngredient(
                            ingredient_id=recipe.ingredient_id,
                            quantity=quantity,
                            unit=recipe.unit,
                        )
                    )

            base_price = (
                branch_product.price
                if branch_product.price is not None
                else product.base_price
            )
            unit_price = (base_price + surcharge).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            order_item = OrderItem(
                product_id=product.id,
                name_snapshot=product.name,
                quantity=item["quantity"],
                unit_price=unit_price,
                ingredients=ingredient_records,
            )
            order_items.append(order_item)
            total_price += unit_price * item["quantity"]

        total_price = total_price.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        # The tip is a share of the donuts only, not of the add-ons.
        tip_amount = _tip_for(total_price, tip_percent)
        total_price += extras.amount
        order = Order(
            user_id=user.id if user is not None else None,
            branch_id=branch_id,
            status=OrderStatus.PENDING,
            fulfillment_type=fulfillment_type,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            delivery_address=delivery_address,
            total_price=total_price,
            table_number=table_number,
            tip_amount=tip_amount,
            gift_box=extras.gift_box,
            candles=extras.candles,
            postcard_message=extras.postcard_message,
            extras_amount=extras.amount,
            scheduled_date=scheduled_day,
            time_slot=time_slot,
            payment_method=payment_method,
            payment_status=(
                PaymentStatus.PENDING
                if payment_method == PaymentMethod.ONLINE
                else PaymentStatus.UNPAID
            ),
            items=order_items,
        )
        session.add(order)
        session.flush()
        order_id = order.id
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create order",
        )

    next_page = "pay" if payment_method == PaymentMethod.ONLINE else "receipt"
    response = RedirectResponse(
        url=f"/en/orders/{order_id}/{next_page}",
        status_code=303,
    )
    # This browser placed the order, so it may open its receipt and pay.
    _remember_order(response, order)
    return response


# ---------- QR codes and test-mode online payment (Expirenza-style) ----------


@app.get("/qr/{branch_code}")
def qr_entry(
    branch_code: str,
    table: int | None = None,
    session: Session = Depends(get_session),
):
    """Landing URL printed in a QR code: opens the menu of that branch (and table)."""
    branch = session.scalar(select(Branch).where(Branch.code == branch_code))
    if branch is None:
        raise HTTPException(404, "Branch not found")

    if table is None:
        return RedirectResponse(
            url=f"/en/store?{urlencode({'branch': branch.code})}",
            status_code=303,
        )

    if not 1 <= table <= MAX_TABLE_NUMBER:
        raise HTTPException(400, "Invalid table number")

    # Table codes open the guest "table home": menu, bill and payment for this table.
    return RedirectResponse(
        url=f"/en/table?{urlencode({'branch': branch.code, 'table': table})}",
        status_code=303,
    )


@app.get("/en/table")
def table_home(request: Request, user: User | None = Depends(get_current_user)):
    """Mobile start screen after scanning a table QR code (filled in by branch.js / table.js)."""
    return _render_template(request, "en/table.html")


def _get_order(session: Session, order_id: int) -> Order:
    order = session.scalar(
        select(Order)
        .options(
            joinedload(Order.branch),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
        .where(Order.id == order_id)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


ORDER_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # a month: long enough to track any pre-order


def _order_cookie_name(order_id: int) -> str:
    return f"donnie_order_{order_id}"


def _token_ok(order: Order, token: str | None) -> bool:
    if not token or not order.access_token:
        return False
    return secrets.compare_digest(token.encode(), order.access_token.encode())


def _can_open_order(
    request: Request, order: Order, user: User | None, token: str | None = None
) -> bool:
    """Who may see an order's receipt, payment and status pages: the browser
    that placed it (cookie), anyone with the emailed link (?t=), the account
    that placed it, the owner and the managers of its branch."""
    if _token_ok(order, token):
        return True
    if _token_ok(order, request.cookies.get(_order_cookie_name(order.id))):
        return True
    if user is None:
        return False
    if order.user_id is not None and order.user_id == user.id:
        return True
    if is_owner(user):
        return True
    return any(branch.id == order.branch_id for branch in get_managed_branches(user))


def _require_order_access(
    request: Request, order: Order, user: User | None, token: str | None = None
) -> None:
    # 404, not 403: a stranger shouldn't even learn that the order exists.
    if not _can_open_order(request, order, user, token):
        raise HTTPException(status_code=404, detail="Order not found")


def _remember_order(response, order: Order) -> None:
    response.set_cookie(
        key=_order_cookie_name(order.id),
        value=order.access_token,
        max_age=ORDER_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )


_PAYABLE_STATUSES = (PaymentStatus.PENDING, PaymentStatus.FAILED)


def _tip_for(total: Decimal, percent: int) -> Decimal:
    return (total * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@app.get("/en/orders/{order_id}/pay")
def order_payment_page(
    request: Request,
    order_id: int,
    declined: bool = False,
    t: str | None = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    order = _get_order(session, order_id)
    _require_order_access(request, order, user, t)
    if (
        order.payment_method != PaymentMethod.ONLINE
        or order.payment_status not in _PAYABLE_STATUSES
    ):
        return RedirectResponse(url=f"/en/orders/{order.id}/receipt", status_code=303)

    current_tip = 0
    if order.total_price > 0:
        percent = int(
            (order.tip_amount * 100 / order.total_price).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        current_tip = percent if percent in TIP_PERCENTAGES else 0

    tip_options = [
        {
            "percent": percent,
            "amount": _tip_for(order.total_price, percent),
        }
        for percent in TIP_PERCENTAGES
    ]

    return _render_template(
        request,
        "en/payment.html",
        {
            "order": order,
            "declined": declined,
            "tip_options": tip_options,
            "current_tip": current_tip,
            "provider_label": (
                "LiqPay · demo" if liqpay.is_demo()
                else "LiqPay · sandbox" if liqpay.is_sandbox()
                else "LiqPay"
            ),
            "provider_demo": liqpay.is_demo(),
        },
    )


def _public_base(request: Request) -> str:
    return liqpay.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _lan_ip() -> str | None:
    """This computer's address on the local network (e.g. 192.168.0.170).
    Connecting a UDP socket only picks the outgoing interface; nothing is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))  # TEST-NET address, never routed
            ip = probe.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def _phone_base(request: Request) -> str:
    """Where a QR code should point so a phone can open it: PUBLIC_BASE_URL
    when set; otherwise this site's address, except that 127.0.0.1/localhost
    (which on a phone means the phone itself) becomes the computer's Wi-Fi
    address. Then a phone on the same Wi-Fi reaches the dev server, as long
    as uvicorn listens on the network (--host 0.0.0.0)."""
    if liqpay.PUBLIC_BASE_URL:
        return liqpay.PUBLIC_BASE_URL
    url = request.url
    if url.hostname in _LOCAL_HOSTS:
        ip = _lan_ip()
        if ip:
            port = f":{url.port}" if url.port else ""
            return f"{url.scheme}://{ip}{port}"
    return str(request.base_url).rstrip("/")


def _callback_url(request: Request) -> str | None:
    base = _public_base(request)
    # The real LiqPay can't reach a laptop: without a public address the
    # result comes from the status request when the guest returns instead.
    if not liqpay.is_demo() and ("localhost" in base or "127.0.0.1" in base):
        return None
    return f"{base}/payments/liqpay/callback"


def _queue_receipt_email(
    background_tasks: BackgroundTasks,
    session: Session,
    order: Order | None,
    request: Request,
) -> None:
    """Emails the payment receipt once LiqPay has confirmed the payment.
    Call it after the payment is committed. The letter is sent after the
    response, so a slow or broken mail server never holds up the guest."""
    if order is None:
        return
    try:
        if not mailer.claim_receipt(session, order):
            return
        message = mailer.build_receipt(
            order,
            f"{_public_base(request)}/{request.state.language}"
            f"/orders/{order.id}/receipt?t={order.access_token}",
        )
    except Exception:
        mailer.log.exception("Could not prepare the receipt for order #%s", order.id)
        session.rollback()
        mailer.release_receipt(session.get_bind(), order.id)
        return
    background_tasks.add_task(
        mailer.deliver_receipt, message, session.get_bind(), order.id
    )


def _order_by_reference(session: Session, reference: str | None) -> Order | None:
    if not reference:
        return None
    return session.scalar(
        select(Order)
        .options(joinedload(Order.branch), selectinload(Order.items))
        .where(Order.payment_reference == reference)
    )


@app.post("/orders/{order_id}/pay")
def order_payment_submit(
    request: Request,
    order_id: int,
    tip_percent: Annotated[int | None, Form()] = None,
    t: str | None = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    """Starts a LiqPay payment for the amount due and sends the guest to the
    LiqPay checkout. The guest can still change the tip on our screen."""
    if tip_percent is not None and tip_percent not in TIP_PERCENTAGES:
        raise HTTPException(400, "Invalid tip")

    order = _get_order(session, order_id)
    _require_order_access(request, order, user, t)
    if order.payment_method != PaymentMethod.ONLINE:
        raise HTTPException(400, "This order is paid on receipt")
    if order.payment_status not in _PAYABLE_STATUSES:
        return RedirectResponse(url=f"/en/orders/{order.id}/receipt", status_code=303)

    if tip_percent is not None:
        order.tip_amount = _tip_for(order.total_price, tip_percent)

    # LiqPay wants a new order_id for every attempt (a retry after a decline
    # or a changed tip is a new payment).
    order.payment_reference = f"donnie-{order.id}-{secrets.token_hex(4)}"
    order.payment_amount = order.amount_due
    order.payment_provider_id = None
    order.payment_status = PaymentStatus.PENDING
    base = _public_base(request)
    checkout = liqpay.get_client().checkout(
        order_id=order.payment_reference,
        amount=order.payment_amount,
        description=f"Donnie order #{order.id}, {order.branch.name}",
        # The token rides along so the guest's browser gets its receipt back
        # even if it dropped our cookie on the way through LiqPay.
        result_url=(
            f"{base}/ua/orders/{order.id}/payment-return?t={order.access_token}"
            if request.state.language == "ua"
            else f"{base}/orders/{order.id}/payment-return?t={order.access_token}"
        ),
        server_url=_callback_url(request),
    )
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(500, "Could not start the payment")

    # The animated Pay button asks for JSON and posts the form itself.
    if "application/json" in request.headers.get("accept", ""):
        return {"checkout": {"url": checkout.url, "data": checkout.data,
                             "signature": checkout.signature}}
    return _render_template(
        request, "en/liqpay_redirect.html", {"checkout": checkout}
    )


@app.api_route("/orders/{order_id}/payment-return", methods=["GET", "POST"])
def order_payment_return(
    request: Request,
    order_id: int,
    background_tasks: BackgroundTasks,
    t: str | None = None,
    session: Session = Depends(get_session),
):
    """LiqPay sends the guest back here (result_url). We ask LiqPay for the
    payment status ourselves, so it works even when no callback reached us.
    It shows nothing about the order itself, so it needs no access check;
    the pages it redirects to do."""
    order = _get_order(session, order_id)
    if order.payment_reference:
        try:
            result = liqpay.get_client().status(session, order.payment_reference)
            liqpay.apply_payment(order, result)
            session.commit()
        except liqpay.LiqpayError:
            session.rollback()

    if order.payment_status == PaymentStatus.PAID:
        _queue_receipt_email(background_tasks, session, order, request)
        url = f"/en/orders/{order.id}/receipt?paid=1"
    elif order.payment_status == PaymentStatus.FAILED:
        url = f"/en/orders/{order.id}/pay?declined=1"
    elif order.payment_status == PaymentStatus.PENDING:
        url = f"/en/orders/{order.id}/pay"
    else:
        url = f"/en/orders/{order.id}/receipt"
    response = RedirectResponse(url=url, status_code=303)
    if _token_ok(order, t):
        _remember_order(response, order)
    return response


@app.post("/payments/liqpay/callback")
def liqpay_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    data: Annotated[str, Form()],
    signature: Annotated[str, Form()],
    session: Session = Depends(get_session),
):
    """LiqPay's server_url: data + signature, signed with our private key."""
    if not liqpay.handle_callback(session, data, signature):
        session.rollback()
        return JSONResponse({"ok": False}, status_code=400)
    session.commit()
    # The signature is valid, so data decodes; it names the payment attempt.
    reference = liqpay.decode_data(data).get("order_id")
    _queue_receipt_email(
        background_tasks, session, _order_by_reference(session, reference), request
    )
    return {"ok": True}


# ---------- built-in LiqPay emulator (PAYMENT_PROVIDER=demo) ----------


def _demo_liqpay():
    client = liqpay.get_client()
    if not isinstance(client, liqpay.DemoLiqpayClient):
        raise HTTPException(404, "The demo checkout is off")
    return client


@app.post("/demo-liqpay/checkout")
def demo_liqpay_checkout(
    data: Annotated[str, Form()],
    signature: Annotated[str, Form()],
    session: Session = Depends(get_session),
):
    """Where the browser POSTs the checkout form, like LiqPay's /api/3/checkout."""
    client = _demo_liqpay()
    try:
        payment = client.open_checkout(session, data, signature)
    except (liqpay.LiqpayError, ValueError, KeyError):
        session.rollback()
        raise HTTPException(400, "Invalid LiqPay checkout data")
    session.commit()
    return RedirectResponse(url=f"/en/demo-liqpay/pay/{payment.order_id}", status_code=303)


@app.get("/en/demo-liqpay/pay/{reference}")
def demo_liqpay_page(
    request: Request,
    reference: str,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    payment = _demo_liqpay().get_payment(session, reference)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    return _render_template(
        request, "en/demo_liqpay.html", {"payment": payment}
    )


@app.post("/demo-liqpay/pay/{reference}")
def demo_liqpay_pay(
    request: Request,
    reference: str,
    background_tasks: BackgroundTasks,
    card: Annotated[str, Form()],
    session: Session = Depends(get_session),
):
    """The demo checkout's buttons: one of LiqPay's test cards, or cancel."""
    client = _demo_liqpay()
    payment = client.get_payment(session, reference)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    if card not in ("4242424242424242", "4000000000000002", "cancel"):
        raise HTTPException(400, "Unknown test card")
    if payment.status == "created" and card != "cancel":
        client.pay(session, payment, card)
        session.commit()
        # pay() ran the signed callback; like the real one, it sends the receipt.
        _queue_receipt_email(
            background_tasks, session, _order_by_reference(session, reference), request
        )
    return RedirectResponse(url=payment.result_url, status_code=303)


@app.get("/orders/{order_id}/status")
def order_status(
    request: Request,
    order_id: int,
    t: str | None = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    """Current tracker state, polled by the open receipt page."""
    order = _get_order(session, order_id)
    _require_order_access(request, order, user, t)
    return {
        "status": order.status.value,
        "progress": order_progress(order),
    }


@app.post("/manager/orders/{order_id}/status")
def change_order_status(
    order_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    action: Annotated[str, Form()],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(user, branch_id, Permission.MANAGER_PANEL)
    order = _get_order(session, order_id)
    if order.branch_id != branch.id:
        raise HTTPException(403, "This order belongs to another branch")

    order.status = OrderStatus(new_status_after(order, action))
    _commit_manager_change(session)
    return RedirectResponse(
        url=f"/en/manager?branch_id={branch.id}&notice=order-status#order-{order.id}",
        status_code=303,
    )


@app.post("/manager/orders/{order_id}/refund")
def refund_order(
    order_id: int,
    branch_id: Annotated[int, Form(gt=0)],
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    branch = _require_manager_branch(user, branch_id, Permission.MANAGER_PANEL)
    order = _get_order(session, order_id)
    if order.branch_id != branch.id:
        raise HTTPException(403, "This order belongs to another branch")
    if (
        order.payment_method != PaymentMethod.ONLINE
        or order.payment_status != PaymentStatus.PAID
    ):
        raise HTTPException(400, "Only paid online orders can be refunded")

    if order.payment_reference:
        try:
            result = liqpay.get_client().refund(
                session, order.payment_reference, order.payment_amount
            )
        except liqpay.LiqpayError:
            session.rollback()
            raise HTTPException(502, "LiqPay could not refund this payment")
        if result.get("status") in liqpay.FAILED_STATUSES:
            raise HTTPException(502, "LiqPay declined the refund")

    order.payment_status = PaymentStatus.REFUNDED
    order.refunded_at = order.refunded_at or datetime.now(timezone.utc)
    _commit_manager_change(session)
    return RedirectResponse(
        url=f"/en/manager?branch_id={branch.id}&notice=order-refunded#orders",
        status_code=303,
    )
