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

    rfq = RFQ(
        reference="RFQ-1008",
        customer_id=acme.id,
        origin="Yiwu, China",
        destination="Nhava Sheva, India",
        load_type=LoadType.LCL,
        service_type="Warehouse-to-Warehouse",
        notes="Consolidate three suppliers. Inspection required before stuffing.",
        status=RFQStatus.quoted,
        created_at=datetime.utcnow() - timedelta(days=4),
    )
    db.add(rfq)
    db.flush()
    s1 = RFQSupplier(rfq_id=rfq.id, name="Yiwu Bright Hardware", code="SUP-A", city="Yiwu")
    s2 = RFQSupplier(rfq_id=rfq.id, name="Ningbo Glass Co", code="SUP-B", city="Ningbo")
    db.add_all([s1, s2])
    db.flush()
    db.add_all([
        RFQProduct(supplier_id=s1.id, name="Cabinet hinges", hs_code="8302.10", quantity=2000, unit="pcs", unit_price=0.42, weight_kg=320, cbm=1.6),
        RFQProduct(supplier_id=s1.id, name="Drawer slides", hs_code="8302.42", quantity=800, unit="sets", unit_price=1.15, weight_kg=180, cbm=1.1),
        RFQProduct(supplier_id=s2.id, name="Tempered shelf glass", hs_code="7007.19", quantity=400, unit="pcs", weight_kg=300, unit_price=3.4, cbm=2.4),
    ])
    quote = Quote(
        reference="QTE-2041",
        rfq_id=rfq.id,
        amount=1860,
        currency="USD",
        service_type="Warehouse-to-Warehouse",
        origin="Yiwu, China",
        destination="Nhava Sheva, India",
        transit="18–22 days after sailing",
        included="Pickup from three suppliers, export customs, LCL freight, destination THC",
        excluded="Destination duty, last-mile delivery beyond CFS",
        documents_required="Commercial invoice, packing list, supplier KYC",
        instructions="Mark cartons with supplier code.",
        payment_term=PaymentTerm.pay_on_delivery,
        status=QuoteStatus.sent,
        created_by=users[2].id,
    )
    db.add(quote)

    ship = Shipment(
        reference="SHP-1001",
        public_token="trk_8f3a21",
        customer_id=acme.id,
        origin="Ningbo, China",
        destination="Chennai, India",
        load_type=LoadType.LCL,
        service_type="Door-to-Door",
        source="direct",
        status="In Sailing / In Transit",
        payment_term=PaymentTerm.pay_on_delivery,
        amount=2420,
        currency="USD",
        created_at=datetime.utcnow() - timedelta(days=12),
    )
    db.add(ship)
    db.flush()
    ss = ShipmentSupplier(shipment_id=ship.id, name="Shenzhen LED Works", code="SUP-C")
    db.add(ss)
    db.flush()
    db.add(ShipmentProduct(supplier_id=ss.id, name="LED drivers", hs_code="8504.40", quantity=600, unit="pcs", unit_price=4.2, weight_kg=500, cbm=3.2))
    for i, status in enumerate(STATUSES[:9]):
        db.add(StatusEvent(
            shipment_id=ship.id,
            status=status,
            note="Recorded by ops" if i else "Direct shipment opened",
            actor="Omar Ops",
            created_at=datetime.utcnow() - timedelta(days=12 - i),
        ))
    db.add_all([
        Document(shipment_id=ship.id, name="Commercial Invoice", kind="invoice", status=DocStatus.approved),
        Document(shipment_id=ship.id, name="Packing List", kind="packing_list", status=DocStatus.approved),
        Document(shipment_id=ship.id, name="Supplier KYC", kind="kyc", status=DocStatus.under_review),
    ])
    db.add(Message(customer_id=acme.id, author="Priya Shah", role="customer", channel="support", body="Can we add the Ningbo glass to the next sailing?"))
    db.add(Message(customer_id=acme.id, author="Leela Support", role="support", channel="support", body="Yes. Send the packing photos and ops will quote it on RFQ-1008."))
    db.commit()
