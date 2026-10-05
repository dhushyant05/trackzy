import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import (
    STATUSES,
    Customer,
    Document,
    DocStatus,
    LoadType,
    Message,
    PaymentTerm,
    Quote,
    QuoteStatus,
    RFQ,
    RFQProduct,
    RFQStatus,
    RFQSupplier,
    Role,
    Shipment,
    ShipmentProduct,
    ShipmentSupplier,
    StatusEvent,
    User,
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def new_ref(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def seed(db: Session) -> None:
    if db.query(User).filter(User.email == "support@trackzy.test").first() is None and db.query(User).first():
        db.add(User(name="Leela Support", email="support@trackzy.test", password_hash=hash_password("support123"), role=Role.support))
        db.commit()
    if db.query(User).first():
        return

    acme = Customer(company="Acme Imports", contact_name="Priya Shah", email="priya@acme.example", phone="+91 98400 11001", country="India")
    lotus = Customer(company="Lotus Retail", contact_name="Arun Mehta", email="arun@lotus.example", phone="+91 98200 22002", country="India")
    db.add_all([acme, lotus])
    db.flush()

    users = [
        User(name="Asha Admin", email="admin@trackzy.test", password_hash=hash_password("admin123"), role=Role.admin),
        User(name="Mira Manager", email="manager@trackzy.test", password_hash=hash_password("manager123"), role=Role.manager_ops),
        User(name="Omar Ops", email="ops@trackzy.test", password_hash=hash_password("ops123"), role=Role.ops),
        User(name="Priya Shah", email="customer@trackzy.test", password_hash=hash_password("customer123"), role=Role.customer, customer_id=acme.id),
        User(name="Leela Support", email="support@trackzy.test", password_hash=hash_password("support123"), role=Role.support),
    ]
    db.add_all(users)
    db.flush()
    db.commit()
