from uuid import UUID
from sqlalchemy import (
    BigInteger,
    Boolean,
    Integer,
    Uuid,
    String,
    Text,
    Numeric,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    sku: Mapped[str] = mapped_column(String(50))
    product_name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))
    stock_quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    order_number: Mapped[str] = mapped_column(String(30))
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.customer_id")
    )
    order_date: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now()
    )
    order_status: Mapped[str] = mapped_column(String(20))


class OrderDetail(Base):
    __tablename__ = "order_details"

    order_detail_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.order_id", ondelete="CASCADE")
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product_id")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))
    discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2)
    )


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.order_id", ondelete="CASCADE")
    )
    payment_date: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now()
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(30))
    payment_status: Mapped[str] = mapped_column(String(20))


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    guest_session_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    schema_name: Mapped[str] = mapped_column(
        String(63), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="ready", nullable=False
    )
    table_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    row_count: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
