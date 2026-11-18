import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Base, get_session
from app.deps import get_current_user
from app.main import app
from app.models import Branch, User, UserRole
from app.permissions import (
    Permission,
    get_managed_branches,
    has_permission,
    is_manager,
    is_owner,
)


@pytest.fixture
def access_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as session:
        branches = [
            Branch(
                code="NORTH",
                name="North Branch",
                city="Kyiv",
                address="North address",
            ),
            Branch(
                code="SOUTH",
                name="South Branch",
                city="Lviv",
                address="South address",
            ),
            Branch(
                code="OTHER",
                name="Other Branch",
                city="Odesa",
                address="Other address",
            ),
        ]
        customer = User(
            first_name="Casey",
            last_name="Customer",
            email="customer@example.com",
            password_hash="test-hash",
            role=UserRole.CUSTOMER,
        )
        manager = User(
            first_name="Morgan",
            last_name="Manager",
            email="manager@example.com",
            password_hash="test-hash",
            role=UserRole.MANAGER,
            managed_branches=branches[:2],
        )
        single_branch_manager = User(
            first_name="Sam",
            last_name="Manager",
            email="single-manager@example.com",
            password_hash="test-hash",
            role=UserRole.MANAGER,
            managed_branches=[branches[1]],
        )
        unassigned_manager = User(
            first_name="Alex",
            last_name="Manager",
            email="unassigned@example.com",
            password_hash="test-hash",
            role=UserRole.MANAGER,
        )
        owner = User(
            first_name="Olivia",
            last_name="Owner",
            email="owner@example.com",
            password_hash="test-hash",
            role=UserRole.OWNER,
            managed_branches=[branches[2]],
        )
        session.add_all(
            [
                *branches,
                customer,
                manager,
                single_branch_manager,
                unassigned_manager,
                owner,
            ]
        )
        session.commit()
        users = {
            "customer": customer,
            "manager": manager,
            "single_branch_manager": single_branch_manager,
            "unassigned_manager": unassigned_manager,
            "owner": owner,
        }
        branch_ids = {branch.code: branch.id for branch in branches}

    def override_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, follow_redirects=False) as client:
            yield client, users, branch_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def authenticate(user):
    def provide_user(
        request: Request,
        session: Session = Depends(get_session),
    ):
        current_user = session.get(User, user.id)
        request.state.current_user = current_user
        return current_user

    app.dependency_overrides[get_current_user] = provide_user


def test_permissions_keep_owner_out_of_manager_access(access_context):
    _, users, _ = access_context
    customer = users["customer"]
    manager = users["manager"]
    owner = users["owner"]

    assert not has_permission(customer, Permission.MANAGER_PANEL)
    assert has_permission(manager, Permission.MANAGER_PANEL)
    assert has_permission(manager, Permission.UPDATE_PRODUCT_AVAILABILITY)
    assert has_permission(manager, Permission.UPDATE_INGREDIENT_AVAILABILITY)
    assert not has_permission(manager, Permission.OWNER_PANEL)
    assert has_permission(owner, Permission.OWNER_PANEL)
    assert not has_permission(owner, Permission.MANAGER_PANEL)
    assert is_manager(manager)
    assert not is_manager(owner)
    assert is_owner(owner)
    assert not is_owner(manager)
    assert get_managed_branches(owner) == []


@pytest.mark.parametrize(
    ("role", "expected_button", "absent_button"),
    [
        ("manager", "Manager Panel", "Owner Panel"),
        ("owner", "Owner Panel", "Manager Panel"),
        ("customer", None, None),
    ],
)
def test_profile_shows_only_role_appropriate_panel_button(
    access_context,
    role,
    expected_button,
    absent_button,
):
    client, users, _ = access_context
    authenticate(users[role])

    response = client.get("/profile")

    assert response.status_code == 200
    if expected_button:
        assert response.text.count(expected_button) == 1
        assert response.text.count(absent_button) == 0
    else:
        assert "Manager Panel" not in response.text
        assert "Owner Panel" not in response.text


def test_unauthenticated_users_are_redirected_from_both_panels(access_context):
    client, _, _ = access_context

    manager_response = client.get("/manager")
    owner_response = client.get("/owner")

    assert manager_response.status_code == 303
    assert manager_response.headers["location"] == "/login"
    assert owner_response.status_code == 303
    assert owner_response.headers["location"] == "/login"


def test_customer_and_owner_cannot_access_manager_panel(access_context):
    client, users, _ = access_context

    authenticate(users["customer"])
    assert client.get("/manager").status_code == 403
    assert client.get("/owner").status_code == 403

    authenticate(users["owner"])
    assert client.get("/manager").status_code == 403
    assert client.get("/owner").status_code == 200


def test_manager_panel_uses_only_assigned_branches(access_context):
    client, users, branch_ids = access_context
    authenticate(users["manager"])
    client.cookies.set("selected_branch", "OTHER")

    default_response = client.get("/manager")
    selected_response = client.get(
        "/manager",
        params={"branch_id": branch_ids["SOUTH"]},
    )
    unassigned_response = client.get(
        "/manager",
        params={"branch_id": branch_ids["OTHER"]},
    )

    assert default_response.status_code == 200
    assert "You are managing North Branch." in default_response.text
    assert "Changes will apply to this branch." in default_response.text
    assert selected_response.status_code == 200
    assert "You are managing South Branch." in selected_response.text
    assert unassigned_response.status_code == 403


def test_single_branch_manager_is_assigned_automatically(access_context):
    client, users, _ = access_context
    authenticate(users["single_branch_manager"])

    response = client.get("/manager")

    assert response.status_code == 200
    assert "You are managing South Branch." in response.text


def test_manager_without_assigned_branches_is_denied(access_context):
    client, users, _ = access_context
    authenticate(users["unassigned_manager"])

    assert client.get("/manager").status_code == 403
