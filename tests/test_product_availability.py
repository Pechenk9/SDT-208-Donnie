import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Base, get_session
from app.deps import get_current_branch
from app.main import app
from app.models import Branch, BranchProduct, Product


@pytest.fixture
def product_detail_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as session:
        branch = Branch(
            code="DETAIL",
            name="Detail Branch",
            city="Kyiv",
            address="Detail address",
        )
        product = Product(
            name="Availability Test Donut",
            base_price=3,
            is_active=True,
        )
        session.add_all([branch, product])
        session.commit()
        branch_id = branch.id
        product_id = product.id

    selected_branch = {"value": None}

    def override_session():
        with test_sessions() as session:
            yield session

    def override_branch():
        return selected_branch["value"]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_branch] = override_branch
    try:
        with TestClient(app, follow_redirects=False) as client:
            yield client, test_sessions, selected_branch, branch_id, product_id
    finally:
        app.dependency_overrides.pop(get_current_branch, None)
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize(
    ("branch_selected", "association_available", "expected_status"),
    [
        (False, None, "Select a branch to check availability"),
        (True, None, "Not available at Detail Branch"),
        (True, True, "Available at Detail Branch"),
        (True, False, "Not available at Detail Branch"),
    ],
)
def test_product_detail_availability(
    product_detail_context,
    branch_selected,
    association_available,
    expected_status,
):
    client, test_sessions, selected_branch, branch_id, product_id = (
        product_detail_context
    )
    with test_sessions() as session:
        branch = session.get(Branch, branch_id)
        if branch_selected:
            selected_branch["value"] = branch
        if association_available is not None:
            session.add(
                BranchProduct(
                    branch_id=branch_id,
                    product_id=product_id,
                    is_available=association_available,
                )
            )
            session.commit()

    response = client.get(f"/product/{product_id}")

    assert response.status_code == 200
    assert expected_status in response.text
