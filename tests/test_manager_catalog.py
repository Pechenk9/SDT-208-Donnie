from decimal import Decimal

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Base, get_session
from app.deps import get_current_user
from app.main import app
from app.models import (
    Branch,
    BranchIngredient,
    BranchProduct,
    Ingredient,
    IngredientGroup,
    Product,
    ProductIngredient,
    User,
    UserRole,
)


@pytest.fixture
def manager_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as session:
        branch_a = Branch(
            code="MANAGED",
            name="Managed Branch",
            city="Kyiv",
            address="Managed address",
        )
        branch_b = Branch(
            code="UNMANAGED",
            name="Unmanaged Branch",
            city="Lviv",
            address="Unmanaged address",
        )
        group = IngredientGroup(name="Manager Test Group", max_selections=2)
        shared_ingredient = Ingredient(
            name="Shared Ingredient",
            group=group,
            extra_price=Decimal("0.12"),
            is_active=True,
        )
        other_ingredient = Ingredient(
            name="Other Branch Ingredient",
            group=group,
            extra_price=Decimal("0.20"),
            is_active=True,
        )
        catalogue_ingredient = Ingredient(
            name="Catalogue Ingredient",
            group=group,
            extra_price=Decimal("0.30"),
            is_active=True,
        )
        shared_product = Product(
            name="Shared Product",
            base_price=Decimal("2.50"),
            is_active=True,
        )
        shared_product.recipe = [
            ProductIngredient(
                ingredient=shared_ingredient,
                default_quantity=Decimal("5"),
                max_quantity=Decimal("10"),
                is_changeable=True,
                unit="g",
            )
        ]
        other_product = Product(
            name="Other Branch Product",
            base_price=Decimal("3.50"),
            is_active=True,
        )
        catalogue_product = Product(
            name="Catalogue Product",
            base_price=Decimal("4.50"),
            is_active=True,
        )
        manager = User(
            first_name="Branch",
            last_name="Manager",
            email="manager-catalog@example.com",
            password_hash="test-hash",
            role=UserRole.MANAGER,
            managed_branches=[branch_a],
        )
        customer = User(
            first_name="Store",
            last_name="Customer",
            email="customer-catalog@example.com",
            password_hash="test-hash",
            role=UserRole.CUSTOMER,
        )
        owner = User(
            first_name="Network",
            last_name="Owner",
            email="owner-catalog@example.com",
            password_hash="test-hash",
            role=UserRole.OWNER,
        )
        session.add_all(
            [
                branch_a,
                branch_b,
                shared_ingredient,
                other_ingredient,
                catalogue_ingredient,
                shared_product,
                other_product,
                catalogue_product,
                manager,
                customer,
                owner,
                BranchProduct(
                    branch=branch_a,
                    product=shared_product,
                    is_available=True,
                    price=Decimal("3.75"),
                ),
                BranchProduct(
                    branch=branch_b,
                    product=shared_product,
                    is_available=False,
                    price=Decimal("4.25"),
                ),
                BranchProduct(
                    branch=branch_b,
                    product=other_product,
                    is_available=True,
                ),
                BranchIngredient(
                    branch=branch_a,
                    ingredient=shared_ingredient,
                    is_available=True,
                ),
                BranchIngredient(
                    branch=branch_b,
                    ingredient=shared_ingredient,
                    is_available=False,
                ),
                BranchIngredient(
                    branch=branch_b,
                    ingredient=other_ingredient,
                    is_available=True,
                ),
            ]
        )
        session.commit()
        ids = {
            "branch_a": branch_a.id,
            "branch_b": branch_b.id,
            "manager": manager.id,
            "customer": customer.id,
            "owner": owner.id,
            "group": group.id,
            "shared_product": shared_product.id,
            "other_product": other_product.id,
            "catalogue_product": catalogue_product.id,
            "shared_ingredient": shared_ingredient.id,
            "other_ingredient": other_ingredient.id,
            "catalogue_ingredient": catalogue_ingredient.id,
        }

    def override_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, follow_redirects=False) as client:
            yield client, test_sessions, ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def authenticate(user_id):
    def provide_user(
        request: Request,
        session: Session = Depends(get_session),
    ):
        user = session.get(User, user_id)
        request.state.current_user = user
        return user

    app.dependency_overrides[get_current_user] = provide_user


def test_manager_dashboard_lists_only_associations_for_selected_branch(
    manager_context,
):
    client, _, ids = manager_context
    authenticate(ids["manager"])

    response = client.get(
        "/manager",
        params={"branch_id": ids["branch_a"]},
    )

    assert response.status_code == 200
    assert "Shared Product" in response.text
    assert response.text.count("Other Branch Product") == 1
    assert "Shared Ingredient" in response.text
    assert response.text.count("Other Branch Ingredient") == 1


def test_manager_dashboard_shows_empty_states_and_single_branch_without_picker(
    manager_context,
):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])
    with test_sessions() as session:
        session.delete(
            session.get(
                BranchProduct,
                (ids["branch_a"], ids["shared_product"]),
            )
        )
        session.delete(
            session.get(
                BranchIngredient,
                (ids["branch_a"], ids["shared_ingredient"]),
            )
        )
        session.commit()

    response = client.get(
        "/manager",
        params={"branch_id": ids["branch_a"]},
    )

    assert response.status_code == 200
    assert "No products are associated with this branch yet." in response.text
    assert "No ingredients are associated with this branch yet." in response.text
    assert "manager-branch-picker" not in response.text


def test_manager_can_add_existing_catalogue_associations(manager_context):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])

    product_response = client.post(
        "/manager/products/add",
        data={
            "branch_id": ids["branch_a"],
            "product_id": ids["catalogue_product"],
        },
    )
    ingredient_response = client.post(
        "/manager/ingredients/add",
        data={
            "branch_id": ids["branch_a"],
            "ingredient_id": ids["catalogue_ingredient"],
        },
    )

    assert product_response.status_code == 303
    assert ingredient_response.status_code == 303
    assert f"branch_id={ids['branch_a']}" in product_response.headers["location"]
    with test_sessions() as session:
        product_link = session.get(
            BranchProduct,
            (ids["branch_a"], ids["catalogue_product"]),
        )
        ingredient_link = session.get(
            BranchIngredient,
            (ids["branch_a"], ids["catalogue_ingredient"]),
        )
        assert product_link is not None
        assert product_link.is_available is True
        assert product_link.price is None
        assert ingredient_link is not None
        assert ingredient_link.is_available is True
        assert session.get(Product, ids["catalogue_product"]).name == "Catalogue Product"
        assert (
            session.get(Ingredient, ids["catalogue_ingredient"]).name
            == "Catalogue Ingredient"
        )


def test_manager_can_update_branch_availability_only(manager_context):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])

    product_response = client.post(
        f"/manager/products/{ids['shared_product']}/availability",
        data={"branch_id": ids["branch_a"], "is_available": "false"},
    )
    ingredient_response = client.post(
        f"/manager/ingredients/{ids['shared_ingredient']}/availability",
        data={"branch_id": ids["branch_a"], "is_available": "false"},
    )

    assert product_response.status_code == 303
    assert ingredient_response.status_code == 303
    with test_sessions() as session:
        product_link_a = session.get(
            BranchProduct,
            (ids["branch_a"], ids["shared_product"]),
        )
        product_link_b = session.get(
            BranchProduct,
            (ids["branch_b"], ids["shared_product"]),
        )
        ingredient_link_a = session.get(
            BranchIngredient,
            (ids["branch_a"], ids["shared_ingredient"]),
        )
        ingredient_link_b = session.get(
            BranchIngredient,
            (ids["branch_b"], ids["shared_ingredient"]),
        )
        product = session.get(Product, ids["shared_product"])
        ingredient = session.get(Ingredient, ids["shared_ingredient"])

        assert product_link_a.is_available is False
        assert product_link_a.price == Decimal("3.75")
        assert product_link_b.is_available is False
        assert product_link_b.price == Decimal("4.25")
        assert product.is_active is True
        assert product.base_price == Decimal("2.50")
        assert ingredient_link_a.is_available is False
        assert ingredient_link_b.is_available is False
        assert ingredient.is_active is True
        assert ingredient.extra_price == Decimal("0.12")


def test_removing_associations_preserves_catalogue_and_other_branch_links(
    manager_context,
):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])

    product_response = client.post(
        f"/manager/products/{ids['shared_product']}/remove",
        data={"branch_id": ids["branch_a"]},
    )
    ingredient_response = client.post(
        f"/manager/ingredients/{ids['shared_ingredient']}/remove",
        data={"branch_id": ids["branch_a"]},
    )

    assert product_response.status_code == 303
    assert ingredient_response.status_code == 303
    with test_sessions() as session:
        assert session.get(Product, ids["shared_product"]) is not None
        assert session.get(Ingredient, ids["shared_ingredient"]) is not None
        assert (
            session.get(BranchProduct, (ids["branch_a"], ids["shared_product"]))
            is None
        )
        assert (
            session.get(
                BranchIngredient,
                (ids["branch_a"], ids["shared_ingredient"]),
            )
            is None
        )
        assert (
            session.get(BranchProduct, (ids["branch_b"], ids["shared_product"]))
            is not None
        )
        assert (
            session.get(
                BranchIngredient,
                (ids["branch_b"], ids["shared_ingredient"]),
            )
            is not None
        )
        assert session.get(
            ProductIngredient,
            (ids["shared_product"], ids["shared_ingredient"]),
        ) is not None


def test_manager_cannot_use_another_branch_id_or_its_association_ids(
    manager_context,
):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])

    forged_add = client.post(
        "/manager/products/add",
        data={
            "branch_id": ids["branch_b"],
            "product_id": ids["catalogue_product"],
        },
    )
    forged_product_update = client.post(
        f"/manager/products/{ids['shared_product']}/availability",
        data={"branch_id": ids["branch_b"], "is_available": "true"},
    )
    forged_product_remove = client.post(
        f"/manager/products/{ids['shared_product']}/remove",
        data={"branch_id": ids["branch_b"]},
    )
    wrong_branch_product = client.post(
        f"/manager/products/{ids['other_product']}/availability",
        data={"branch_id": ids["branch_a"], "is_available": "false"},
    )
    forged_ingredient_update = client.post(
        f"/manager/ingredients/{ids['shared_ingredient']}/availability",
        data={"branch_id": ids["branch_b"], "is_available": "true"},
    )
    wrong_branch_ingredient = client.post(
        f"/manager/ingredients/{ids['other_ingredient']}/remove",
        data={"branch_id": ids["branch_a"]},
    )

    assert forged_add.status_code == 403
    assert forged_product_update.status_code == 403
    assert forged_product_remove.status_code == 403
    assert wrong_branch_product.status_code == 404
    assert forged_ingredient_update.status_code == 403
    assert wrong_branch_ingredient.status_code == 404
    with test_sessions() as session:
        assert session.get(
            BranchProduct,
            (ids["branch_a"], ids["catalogue_product"]),
        ) is None
        assert session.get(
            BranchProduct,
            (ids["branch_b"], ids["shared_product"]),
        ).is_available is False
        assert session.get(
            BranchIngredient,
            (ids["branch_b"], ids["shared_ingredient"]),
        ).is_available is False


def test_duplicate_and_missing_catalogue_additions_are_rejected(manager_context):
    client, _, ids = manager_context
    authenticate(ids["manager"])

    duplicate_product = client.post(
        "/manager/products/add",
        data={
            "branch_id": ids["branch_a"],
            "product_id": ids["shared_product"],
        },
    )
    missing_product = client.post(
        "/manager/products/add",
        data={"branch_id": ids["branch_a"], "product_id": 99999},
    )
    duplicate_ingredient = client.post(
        "/manager/ingredients/add",
        data={
            "branch_id": ids["branch_a"],
            "ingredient_id": ids["shared_ingredient"],
        },
    )
    missing_ingredient = client.post(
        "/manager/ingredients/add",
        data={"branch_id": ids["branch_a"], "ingredient_id": 99999},
    )

    assert duplicate_product.status_code == 409
    assert missing_product.status_code == 404
    assert duplicate_ingredient.status_code == 409
    assert missing_ingredient.status_code == 404


def test_global_deactivation_warnings_do_not_restrict_branch_management(
    manager_context,
):
    client, test_sessions, ids = manager_context
    authenticate(ids["manager"])

    active_response = client.get(
        "/manager",
        params={"branch_id": ids["branch_a"]},
    )
    assert "Owner has deactivated this product globally." not in active_response.text
    assert "Owner has deactivated this ingredient globally." not in active_response.text

    authenticate(ids["owner"])
    product_deactivations = [
        (ids["shared_product"], "Shared Product", "2.50"),
        (ids["catalogue_product"], "Catalogue Product", "4.50"),
    ]
    for product_id, name, price in product_deactivations:
        response = client.post(
            f"/owner/products/{product_id}/edit",
            data={
                "name": name,
                "description": "",
                "base_price": price,
                "calories": "",
                "image_url": "",
                "is_active": "false",
            },
        )
        assert response.status_code == 303

    ingredient_deactivations = [
        (ids["shared_ingredient"], "Shared Ingredient", "0.12"),
        (ids["catalogue_ingredient"], "Catalogue Ingredient", "0.30"),
    ]
    for ingredient_id, name, extra_price in ingredient_deactivations:
        response = client.post(
            f"/owner/ingredients/{ingredient_id}/edit",
            data={
                "name": name,
                "description": "",
                "extra_price": extra_price,
                "group_id": ids["group"],
                "is_active": "false",
            },
        )
        assert response.status_code == 303

    authenticate(ids["manager"])
    inactive_response = client.get(
        "/manager",
        params={"branch_id": ids["branch_a"]},
    )
    assert inactive_response.text.count(
        "Owner has deactivated this product globally."
    ) == 2
    assert inactive_response.text.count(
        "Owner has deactivated this ingredient globally."
    ) == 2

    add_product = client.post(
        "/manager/products/add",
        data={
            "branch_id": ids["branch_a"],
            "product_id": ids["catalogue_product"],
        },
    )
    add_ingredient = client.post(
        "/manager/ingredients/add",
        data={
            "branch_id": ids["branch_a"],
            "ingredient_id": ids["catalogue_ingredient"],
        },
    )
    assert add_product.status_code == 303
    assert add_ingredient.status_code == 303

    update_product = client.post(
        f"/manager/products/{ids['catalogue_product']}/availability",
        data={"branch_id": ids["branch_a"], "is_available": "false"},
    )
    update_ingredient = client.post(
        f"/manager/ingredients/{ids['catalogue_ingredient']}/availability",
        data={"branch_id": ids["branch_a"], "is_available": "false"},
    )
    assert update_product.status_code == 303
    assert update_ingredient.status_code == 303

    with test_sessions() as session:
        assert session.get(Product, ids["shared_product"]).is_active is False
        assert session.get(Product, ids["catalogue_product"]).is_active is False
        assert session.get(Ingredient, ids["shared_ingredient"]).is_active is False
        assert (
            session.get(Ingredient, ids["catalogue_ingredient"]).is_active
            is False
        )

        shared_product_a = session.get(
            BranchProduct,
            (ids["branch_a"], ids["shared_product"]),
        )
        shared_product_b = session.get(
            BranchProduct,
            (ids["branch_b"], ids["shared_product"]),
        )
        added_product = session.get(
            BranchProduct,
            (ids["branch_a"], ids["catalogue_product"]),
        )
        assert shared_product_a.is_available is True
        assert shared_product_a.price == Decimal("3.75")
        assert shared_product_b.is_available is False
        assert shared_product_b.price == Decimal("4.25")
        assert added_product.is_available is False
        assert added_product.price is None

        shared_ingredient_a = session.get(
            BranchIngredient,
            (ids["branch_a"], ids["shared_ingredient"]),
        )
        shared_ingredient_b = session.get(
            BranchIngredient,
            (ids["branch_b"], ids["shared_ingredient"]),
        )
        added_ingredient = session.get(
            BranchIngredient,
            (ids["branch_a"], ids["catalogue_ingredient"]),
        )
        assert shared_ingredient_a.is_available is True
        assert shared_ingredient_b.is_available is False
        assert added_ingredient.is_available is False


@pytest.mark.parametrize("role", ["customer", "owner"])
def test_customer_and_owner_cannot_modify_manager_catalogue(manager_context, role):
    client, _, ids = manager_context
    authenticate(ids[role])
    branch_id = ids["branch_a"]

    responses = [
        client.get("/manager", params={"branch_id": branch_id}),
        client.post(
            "/manager/products/add",
            data={
                "branch_id": branch_id,
                "product_id": ids["catalogue_product"],
            },
        ),
        client.post(
            f"/manager/products/{ids['shared_product']}/availability",
            data={"branch_id": branch_id, "is_available": "false"},
        ),
        client.post(
            f"/manager/products/{ids['shared_product']}/remove",
            data={"branch_id": branch_id},
        ),
        client.post(
            "/manager/ingredients/add",
            data={
                "branch_id": branch_id,
                "ingredient_id": ids["catalogue_ingredient"],
            },
        ),
        client.post(
            f"/manager/ingredients/{ids['shared_ingredient']}/availability",
            data={"branch_id": branch_id, "is_available": "false"},
        ),
        client.post(
            f"/manager/ingredients/{ids['shared_ingredient']}/remove",
            data={"branch_id": branch_id},
        ),
    ]

    assert all(response.status_code == 403 for response in responses)
    if role == "owner":
        assert client.get("/owner").status_code == 200
    else:
        assert client.get("/store").status_code == 200
