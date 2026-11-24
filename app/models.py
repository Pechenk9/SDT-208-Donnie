
from __future__ import annotations

import enum
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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


# Payment is stored as plain strings (with CHECK constraints) so new values
# don't need a PostgreSQL enum migration.
class PaymentMethod:
    ON_RECEIPT = "on_receipt"  # pay at pickup / to the courier
    ONLINE = "online"  # pay on the Donnie payment page (test mode)

    ALL = (ON_RECEIPT, ONLINE)


class PaymentStatus:
    UNPAID = "unpaid"  # pays on receipt
    PENDING = "pending"  # online payment started, not finished
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

    ALL = (UNPAID, PENDING, PAID, FAILED, REFUNDED)


TIP_PERCENTAGES = (0, 5, 10, 15)
MAX_TABLE_NUMBER = 99

# "Make it a celebration" add-ons at checkout (idea from Kyiv cake shops such
# as Milk Bar, where candles, a postcard and gift packaging sit next to the
# order). Prices are decided on the server; the client only shows estimates.
GIFT_BOX_PRICE = Decimal("2.00")  # one gift box with a ribbon for the order
CANDLE_PRICE = Decimal("0.20")  # per candle
MAX_CANDLES = 24
MAX_POSTCARD_LENGTH = 200

# Pre-order windows for pickup and delivery, also borrowed from Kyiv bakeries
# that let you pick a day and a time window instead of "as soon as possible".
TIME_SLOTS = ("09:30-12:00", "12:00-15:00", "15:00-18:00", "18:00-21:00")
MAX_PREORDER_DAYS = 7


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

    login_sessions: Mapped[list[LoginSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="login_sessions",
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

    city_en: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(Text)

    address_en: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

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

    name_en: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    max_selections: Mapped[int] = mapped_column(Integer)

    is_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

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

    name_en: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    description_en: Mapped[str | None] = mapped_column(
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

    name_en: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    description_en: Mapped[str | None] = mapped_column(
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

    # Dine-in order placed from a table QR code (pickup at that table).
    table_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    tip_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        server_default="0",
        nullable=False,
    )

    # Celebration add-ons. extras_amount is already included in total_price.
    gift_box: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    candles: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    postcard_message: Mapped[str | None] = mapped_column(
        String(MAX_POSTCARD_LENGTH),
        nullable=True,
    )

    extras_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        server_default="0",
        nullable=False,
    )

    # Pre-order: both empty means "as soon as possible".
    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    time_slot: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    payment_method: Mapped[str] = mapped_column(
        String(20),
        default=PaymentMethod.ON_RECEIPT,
        server_default=PaymentMethod.ON_RECEIPT,
        nullable=False,
    )

    payment_status: Mapped[str] = mapped_column(
        String(20),
        default=PaymentStatus.UNPAID,
        server_default=PaymentStatus.UNPAID,
        nullable=False,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # LiqPay: order_id of the current payment attempt (unique per attempt),
    # the amount it asked for, and LiqPay's payment_id once it is known.
    payment_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    payment_provider_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Secret that opens this order's receipt, payment and status pages for a
    # guest. Order ids are sequential, so an id alone must not expose customer
    # details.
    access_token: Mapped[str] = mapped_column(
        String(64),
        default=lambda: secrets.token_urlsafe(24),
        nullable=False,
    )

    # Prevents duplicate receipt emails; cleared if delivery fails so it can retry.
    receipt_emailed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    @property
    def amount_due(self) -> Decimal:
        return (self.total_price or Decimal("0")) + (self.tip_amount or Decimal("0"))

    @property
    def donuts_amount(self) -> Decimal:
        return (self.total_price or Decimal("0")) - (self.extras_amount or Decimal("0"))

    @property
    def has_extras(self) -> bool:
        return bool(self.gift_box or self.candles or self.postcard_message)

    __table_args__ = (
        CheckConstraint(
            "total_price >= 0",
            name="ck_orders_total_price",
        ),
        CheckConstraint(
            "tip_amount >= 0",
            name="ck_orders_tip_amount",
        ),
        CheckConstraint(
            "candles >= 0 AND candles <= 24",
            name="ck_orders_candles",
        ),
        CheckConstraint(
            "extras_amount >= 0",
            name="ck_orders_extras_amount",
        ),
        CheckConstraint(
            "(scheduled_date IS NULL) = (time_slot IS NULL)",
            name="ck_orders_schedule_pair",
        ),
        CheckConstraint(
            "table_number IS NULL OR (table_number >= 1 AND table_number <= 99)",
            name="ck_orders_table_number",
        ),
        CheckConstraint(
            "payment_method IN ('on_receipt', 'online')",
            name="ck_orders_payment_method",
        ),
        CheckConstraint(
            "payment_status IN ('unpaid', 'pending', 'paid', 'failed', 'refunded')",
            name="ck_orders_payment_status",
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


class DemoLiqpayPayment(Base):
    """Payments of the built-in LiqPay emulator (PAYMENT_PROVIDER=demo).
    Field names follow the LiqPay API."""

    __tablename__ = "demo_liqpay_payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    currency: Mapped[str] = mapped_column(String(3))

    description: Mapped[str] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(30), default="created")

    result_url: Mapped[str] = mapped_column(Text)

    server_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    card_mask: Mapped[str | None] = mapped_column(String(32), nullable=True)

    err_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    err_description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    create_date: Mapped[int] = mapped_column(BigInteger)

    end_date: Mapped[int] = mapped_column(BigInteger)
