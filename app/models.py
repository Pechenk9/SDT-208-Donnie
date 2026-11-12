
from __future__ import annotations

import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Column,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.config import Base


class UserRole(enum.Enum):
    CUSTOMER = "customer"
    MANAGER = "manager"
    OWNER = "owner"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FulfillmentType(enum.Enum):
    PICKUP = "pickup"
    DELIVERY = "delivery"


branch_managers = Table(
    "branch_managers",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "branch_id",
        ForeignKey("branches.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(String(255))

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
        ),
        default=UserRole.CUSTOMER,
        nullable=False,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    managed_branches: Mapped[list[Branch]] = relationship(
        secondary=branch_managers,
        back_populates="managers",
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="user",
    )


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
    )

    name: Mapped[str] = mapped_column(String(150))

    city: Mapped[str] = mapped_column(String(100))

    address: Mapped[str] = mapped_column(Text)

    phones: Mapped[list[BranchPhone]] = relationship(
        back_populates="branch",
        cascade="all, delete-orphan",
    )

    managers: Mapped[list[User]] = relationship(
        secondary=branch_managers,
        back_populates="managed_branches",
    )

    products: Mapped[list[BranchProduct]] = relationship(
        back_populates="branch",
        cascade="all, delete-orphan",
    )

    ingredients: Mapped[list[BranchIngredient]] = relationship(
        back_populates="branch",
        cascade="all, delete-orphan",
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="branch",
    )


class BranchPhone(Base):
    __tablename__ = "branch_phones"

    id: Mapped[int] = mapped_column(primary_key=True)

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
    )

    phone_number: Mapped[str] = mapped_column(String(30))

    label: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    branch: Mapped[Branch] = relationship(
        back_populates="phones",
    )


class IngredientGroup(Base):
    __tablename__ = "ingredient_groups"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )

    max_selections: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "max_selections > 0",
            name="ck_ingredient_groups_max_selections",
        ),
    )

    ingredients: Mapped[list[Ingredient]] = relationship(
        back_populates="group",
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("ingredient_groups.id", ondelete="RESTRICT"),
    )

    extra_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        server_default="0",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    group: Mapped[IngredientGroup] = relationship(
        back_populates="ingredients",
    )

    product_recipes: Mapped[list[ProductIngredient]] = relationship(
        back_populates="ingredient",
    )

    branch_availability: Mapped[list[BranchIngredient]] = relationship(
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )

    order_usages: Mapped[list[OrderItemIngredient]] = relationship(
        back_populates="ingredient",
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    base_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
    )

    calories: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "base_price >= 0",
            name="ck_products_base_price",
        ),
        CheckConstraint(
            "calories IS NULL OR calories >= 0",
            name="ck_products_calories",
        ),
    )

    recipe: Mapped[list[ProductIngredient]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    branch_availability: Mapped[list[BranchProduct]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    order_items: Mapped[list[OrderItem]] = relationship(
        back_populates="product",
    )


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )

    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    default_quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
    )

    is_changeable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    max_quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
    )

    unit: Mapped[str] = mapped_column(String(30))

    __table_args__ = (
        CheckConstraint(
            "default_quantity >= 0",
            name="ck_product_ingredients_default_quantity",
        ),
        CheckConstraint(
            "max_quantity >= default_quantity",
            name="ck_product_ingredients_max_quantity",
        ),
    )

    product: Mapped[Product] = relationship(
        back_populates="recipe",
    )

    ingredient: Mapped[Ingredient] = relationship(
        back_populates="product_recipes",
    )


class BranchProduct(Base):
    __tablename__ = "branch_products"

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        primary_key=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_branch_products_price",
        ),
    )

    branch: Mapped[Branch] = relationship(
        back_populates="products",
    )

    product: Mapped[Product] = relationship(
        back_populates="branch_availability",
    )


class BranchIngredient(Base):
    __tablename__ = "branch_ingredients"

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        primary_key=True,
    )

    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        primary_key=True,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )

    branch: Mapped[Branch] = relationship(
        back_populates="ingredients",
    )

    ingredient: Mapped[Ingredient] = relationship(
        back_populates="branch_availability",
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
    )

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(
            OrderStatus,
            name="order_status",
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
        ),
        default=OrderStatus.PENDING,
        nullable=False,
    )

    fulfillment_type: Mapped[FulfillmentType] = mapped_column(
        SAEnum(
            FulfillmentType,
            name="fulfillment_type",
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
        ),
        nullable=False,
    )

    customer_name: Mapped[str] = mapped_column(String(200))

    customer_phone: Mapped[str] = mapped_column(String(30))

    customer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    delivery_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "total_price >= 0",
            name="ck_orders_total_price",
        ),
        CheckConstraint(
            "fulfillment_type != 'delivery' OR delivery_address IS NOT NULL",
            name="ck_orders_delivery_address",
        ),
        Index("ix_orders_branch_created", "branch_id", "created_at"),
        Index("ix_orders_status", "status"),
    )

    user: Mapped[User | None] = relationship(
        back_populates="orders",
    )

    branch: Mapped[Branch] = relationship(
        back_populates="orders",
    )

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
    )

    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )

    name_snapshot: Mapped[str] = mapped_column(String(150))

    quantity: Mapped[int] = mapped_column(Integer)

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
    )

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_order_items_unit_price",
        ),
    )

    order: Mapped[Order] = relationship(
        back_populates="items",
    )

    product: Mapped[Product | None] = relationship(
        back_populates="order_items",
    )

    ingredients: Mapped[list[OrderItemIngredient]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
    )


class OrderItemIngredient(Base):
    __tablename__ = "order_item_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
    )

    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
    )

    unit: Mapped[str] = mapped_column(String(30))

    __table_args__ = (
        UniqueConstraint(
            "order_item_id",
            "ingredient_id",
            name="uq_order_item_ingredient",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_order_item_ingredients_quantity",
        ),
    )

    order_item: Mapped[OrderItem] = relationship(
        back_populates="ingredients",
    )

    ingredient: Mapped[Ingredient] = relationship(
        back_populates="order_usages",
    )
