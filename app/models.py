import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Role(str, enum.Enum):
    admin = "admin"
    manager_ops = "manager_ops"
    ops = "ops"
    customer = "customer"
    support = "support"


class RFQStatus(str, enum.Enum):
    submitted = "submitted"
    in_review = "in_review"
    quoted = "quoted"
    accepted = "accepted"
    declined = "declined"


class QuoteStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"


class PaymentTerm(str, enum.Enum):
    pay_on_delivery = "pay_on_delivery"
    partial_advance = "partial_advance"
    full_advance = "full_advance"
    other = "other"


class LoadType(str, enum.Enum):
    FCL = "FCL"
    LCL = "LCL"


class DocStatus(str, enum.Enum):
    required = "required"
    uploaded = "uploaded"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    missing = "missing"


STATUSES = [
    "Waiting for Collection",
    "Collected",
    "Arrived at Warehouse",
    "Pending Inspection",
    "Inspection Completed",
    "Pending Customs Clearance",
    "Customs Cleared",
    "Container Loaded",
    "In Sailing / In Transit",
    "Arrived at Destination",
    "Out for Delivery",
    "Delivered",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    login_name: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[Role] = mapped_column(Enum(Role))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped["Customer | None"] = relationship(back_populates="users")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(180))
    contact_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180))
    phone: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users: Mapped[list[User]] = relationship(back_populates="customer")
    rfqs: Mapped[list["RFQ"]] = relationship(back_populates="customer")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="customer")


class SignupRequest(Base):
    __tablename__ = "signup_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    login_name: Mapped[str] = mapped_column(String(80), index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RFQ(Base):
    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    load_type: Mapped[LoadType] = mapped_column(Enum(LoadType), default=LoadType.LCL)
    service_type: Mapped[str] = mapped_column(String(80), default="Door-to-Door")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RFQStatus] = mapped_column(Enum(RFQStatus), default=RFQStatus.submitted)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped[Customer] = relationship(back_populates="rfqs")
    suppliers: Mapped[list["RFQSupplier"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="rfq")


class RFQSupplier(Base):
    __tablename__ = "rfq_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"))
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(40), default="")
    city: Mapped[str] = mapped_column(String(80), default="")

    rfq: Mapped[RFQ] = relationship(back_populates="suppliers")
    products: Mapped[list["RFQProduct"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class RFQProduct(Base):
    __tablename__ = "rfq_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("rfq_suppliers.id"))
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    hs_code: Mapped[str] = mapped_column(String(32), default="")
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    weight_kg: Mapped[float] = mapped_column(Float, default=0)
    cbm: Mapped[float] = mapped_column(Float, default=0)
    photo_note: Mapped[str] = mapped_column(String(200), default="")

    supplier: Mapped[RFQSupplier] = relationship(back_populates="products")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    service_type: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    transit: Mapped[str] = mapped_column(String(120), default="")
    included: Mapped[str] = mapped_column(Text, default="")
    excluded: Mapped[str] = mapped_column(Text, default="")
    documents_required: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    payment_term: Mapped[PaymentTerm] = mapped_column(Enum(PaymentTerm), default=PaymentTerm.pay_on_delivery)
    status: Mapped[QuoteStatus] = mapped_column(Enum(QuoteStatus), default=QuoteStatus.sent)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    rfq: Mapped[RFQ] = relationship(back_populates="quotes")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    public_token: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id"), nullable=True)
    quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), nullable=True)
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    load_type: Mapped[LoadType] = mapped_column(Enum(LoadType), default=LoadType.LCL)
    service_type: Mapped[str] = mapped_column(String(80), default="Door-to-Door")
    source: Mapped[str] = mapped_column(String(20), default="rfq")
    status: Mapped[str] = mapped_column(String(80), default=STATUSES[0])
    payment_term: Mapped[PaymentTerm] = mapped_column(Enum(PaymentTerm), default=PaymentTerm.pay_on_delivery)
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped[Customer] = relationship(back_populates="shipments")
    suppliers: Mapped[list["ShipmentSupplier"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")
    events: Mapped[list["StatusEvent"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")


class ShipmentSupplier(Base):
    __tablename__ = "shipment_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(40), default="")

    shipment: Mapped[Shipment] = relationship(back_populates="suppliers")
    products: Mapped[list["ShipmentProduct"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class ShipmentProduct(Base):
    __tablename__ = "shipment_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("shipment_suppliers.id"))
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    hs_code: Mapped[str] = mapped_column(String(32), default="")
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    weight_kg: Mapped[float] = mapped_column(Float, default=0)
    cbm: Mapped[float] = mapped_column(Float, default=0)


    supplier: Mapped[ShipmentSupplier] = relationship(back_populates="products")


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    status: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120), default="ops")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    shipment: Mapped[Shipment] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60), default="other")
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.required)
    note: Mapped[str] = mapped_column(Text, default="")

    shipment: Mapped[Shipment] = relationship(back_populates="documents")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    author: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20), default="support")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
