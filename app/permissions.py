from enum import Enum

from app.models import Branch, User, UserRole


class Permission(str, Enum):
    CUSTOMER_STORE = "customer_store"
    MANAGER_PANEL = "manager_panel"
    OWNER_PANEL = "owner_panel"
    UPDATE_PRODUCT_AVAILABILITY = "update_product_availability"
    UPDATE_INGREDIENT_AVAILABILITY = "update_ingredient_availability"


_ROLE_PERMISSIONS = {
    UserRole.CUSTOMER: frozenset(
        {
            Permission.CUSTOMER_STORE,
        }
    ),
    UserRole.MANAGER: frozenset(
        {
            Permission.CUSTOMER_STORE,
            Permission.MANAGER_PANEL,
            Permission.UPDATE_PRODUCT_AVAILABILITY,
            Permission.UPDATE_INGREDIENT_AVAILABILITY,
        }
    ),
    UserRole.OWNER: frozenset(
        {
            Permission.CUSTOMER_STORE,
            Permission.OWNER_PANEL,
        }
    ),
}


def has_permission(user: User | None, action: Permission | str) -> bool:
    if user is None:
        return False

    try:
        permission = Permission(action)
    except ValueError:
        return False

    return permission in _ROLE_PERMISSIONS.get(user.role, ())


def is_manager(user: User | None) -> bool:
    return user is not None and user.role == UserRole.MANAGER


def is_owner(user: User | None) -> bool:
    return user is not None and user.role == UserRole.OWNER


def get_managed_branches(user: User | None) -> list[Branch]:
    if not is_manager(user):
        return []

    return sorted(
        user.managed_branches,
        key=lambda branch: (
            branch.city.casefold(),
            branch.name.casefold(),
            branch.id,
        ),
    )
