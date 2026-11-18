from decimal import InvalidOperation, ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import re
from typing import Annotated
from urllib.parse import urlencode

from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
        url=f"/manager?{query}",
        status_code=303,
    )


@app.get("/manager")
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

    return templates.TemplateResponse(
        request,
        "manager_dashboard.html",
        {
            "managed_branches": managed_branches,
            "selected_branch": selected_branch,
            "branch_products": branch_products,
            "catalogue_products": catalogue_products,
            "branch_ingredients": branch_ingredients,
            "catalogue_ingredients": catalogue_ingredients,
            "notice": _MANAGER_NOTICES.get(notice),
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
) -> dict | None:
    name = name.strip()
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

    if not name or len(name) > 150 or price is None:
        return None

    return {
        "name": name,
        "description": description.strip() or None,
        "base_price": price,
        "calories": parsed_calories,
        "image_url": image_url.strip() or None,
        "is_active": is_active,
    }


def _ingredient_form_values(
    name: str,
    description: str,
    extra_price: str,
    group_id: str,
    is_active: bool,
) -> tuple[dict | None, int | None]:
    name = name.strip()
    price = _parse_owner_money(extra_price)
    parsed_group_id = _parse_owner_id(group_id)
    if not name or len(name) > 150 or price is None or parsed_group_id is None:
        return None, None

    return (
        {
            "name": name,
            "description": description.strip() or None,
            "extra_price": price,
            "group_id": parsed_group_id,
            "is_active": is_active,
        },
        parsed_group_id,
    )


@app.get("/owner")
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

    return templates.TemplateResponse(
        request,
        "management_panel.html",
        {
            "user": user,
            "staff_branches": staff_branches,
            "owner_users": owner_users,
            "managers": managers,
            "products": products,
            "ingredients": ingredients,
            "ingredient_groups": ingredient_groups,
            "notice": _OWNER_NOTICES.get(notice),
            "error": _OWNER_ERRORS.get(error),
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
    base_price: str = Form(default=""),
    calories: str = Form(default=""),
    image_url: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    values = _product_form_values(
        name, description, base_price, calories, image_url, is_active
    )
    if values is None:
        return _owner_redirect("products", error="invalid-form")

    duplicate = session.scalar(
        select(Product.id).where(func.lower(Product.name) == values["name"].lower())
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
        name, description, base_price, calories, image_url, is_active
    )
    if values is None:
        return _owner_redirect("products", error="invalid-form")

    duplicate = session.scalar(
        select(Product.id).where(
            func.lower(Product.name) == values["name"].lower(),
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
    extra_price: str = Form(default=""),
    group_id: str = Form(default=""),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_profile_user),
):
    _require_owner(user)
    values, parsed_group_id = _ingredient_form_values(
        name, description, extra_price, group_id, is_active
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
    if duplicate is not None:
        return _owner_redirect("ingredients", error="duplicate")

    session.add(Ingredient(**values))
    return _commit_owner_change(session, "ingredients", "ingredient-created")


@app.post("/owner/ingredients/{ingredient_id}/edit")
def owner_edit_ingredient(
    ingredient_id: int,
    name: str = Form(default=""),
    description: str = Form(default=""),
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
        name, description, extra_price, group_id, is_active
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
            else branch_product is not None and branch_product.is_available
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
    user: User | None = Depends(get_current_user),
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

    return RedirectResponse(
        url=f"/orders/{order_id}/receipt",
        status_code=303,
    )
