import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from .database import Base, engine, get_db
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
from .seed import check_password, hash_password, new_ref, seed

ROOT = Path(__file__).resolve().parent.parent

Base.metadata.create_all(bind=engine)
if engine.dialect.name == "sqlite":
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(messages)").fetchall()]
        if cols and "channel" not in cols:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN channel VARCHAR(20) DEFAULT 'support'")
with next(get_db()) as _db:
    seed(_db)

app = FastAPI(title="Trackzy", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def user_from_token(token: str, db: Session) -> User:
    if not token or not token.startswith("user:"):
        raise HTTPException(401, "Sign in required")
    try:
        user_id = int(token.split(":", 1)[1])
    except ValueError:
        raise HTTPException(401, "Bad token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def require_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    token = (authorization or "").removeprefix("Bearer ").strip()
    return user_from_token(token, db)


class LoginIn(BaseModel):
    email: str
    password: str


class ProductIn(BaseModel):
    name: str
    description: str = ""
    hs_code: str = ""
    quantity: float = 1
    unit: str = "pcs"
    unit_price: float = 0
    weight_kg: float = 0
    cbm: float = 0
    photo_note: str = ""


class SupplierIn(BaseModel):
    name: str
    code: str = ""
    city: str = ""
    products: list[ProductIn] = Field(default_factory=list)


class RFQIn(BaseModel):
    origin: str
    destination: str
    load_type: LoadType = LoadType.LCL
    service_type: str = "Door-to-Door"
    notes: str = ""
    suppliers: list[SupplierIn]


class QuoteIn(BaseModel):
    amount: float
    currency: str = "USD"
    service_type: str
    origin: str
    destination: str
    transit: str = ""
    included: str = ""
    excluded: str = ""
    documents_required: str = ""
    instructions: str = ""
    payment_term: PaymentTerm = PaymentTerm.pay_on_delivery


class DirectShipmentIn(BaseModel):
    customer_id: int | None = None
    company: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    origin: str
    destination: str
    load_type: LoadType = LoadType.LCL
    service_type: str = "Door-to-Door"
    amount: float = 0
    currency: str = "USD"
    payment_term: PaymentTerm = PaymentTerm.pay_on_delivery
    suppliers: list[SupplierIn] = Field(default_factory=list)


class StatusIn(BaseModel):
    status: str
    note: str = ""


class DocIn(BaseModel):
    name: str
    kind: str = "other"
    status: DocStatus = DocStatus.required


class MessageIn(BaseModel):
    body: str
    customer_id: int | None = None
    channel: str = "support"


def totals(suppliers) -> dict:
    value = weight = cbm = 0.0
    for s in suppliers:
        for p in s.products:
            value += (p.quantity or 0) * (p.unit_price or 0)
            weight += p.weight_kg or 0
            cbm += p.cbm or 0
    return {"value": round(value, 2), "weight_kg": round(weight, 2), "cbm": round(cbm, 2)}


def product_dict(p) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description, "hs_code": p.hs_code,
        "quantity": p.quantity, "unit": p.unit, "unit_price": p.unit_price,
        "weight_kg": p.weight_kg, "cbm": p.cbm,
        "line_value": round((p.quantity or 0) * (p.unit_price or 0), 2),
    }


def supplier_dict(s) -> dict:
    return {
        "id": s.id, "name": s.name, "code": s.code, "city": getattr(s, "city", ""),
        "products": [product_dict(p) for p in s.products], "totals": totals([s]),
    }


def rfq_dict(r: RFQ) -> dict:
    return {
        "id": r.id, "reference": r.reference, "customer": r.customer.company, "customer_id": r.customer_id,
        "origin": r.origin, "destination": r.destination, "load_type": r.load_type.value,
        "service_type": r.service_type, "notes": r.notes, "status": r.status.value,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "suppliers": [supplier_dict(s) for s in r.suppliers], "totals": totals(r.suppliers),
        "quotes": [{
            "id": q.id, "reference": q.reference, "amount": q.amount, "currency": q.currency,
            "service_type": q.service_type, "origin": q.origin, "destination": q.destination,
            "transit": q.transit, "included": q.included, "excluded": q.excluded,
            "documents_required": q.documents_required, "instructions": q.instructions,
            "payment_term": q.payment_term.value, "status": q.status.value,
        } for q in r.quotes],
    }


def shipment_dict(s: Shipment, private: bool) -> dict:
    data = {
        "id": s.id, "reference": s.reference,
        "public_token": s.public_token if private else None,
        "origin": s.origin, "destination": s.destination, "load_type": s.load_type.value,
        "service_type": s.service_type, "source": s.source, "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "timeline": [{
            "status": e.status, "note": e.note, "actor": e.actor,
            "at": e.created_at.isoformat() if e.created_at else None,
        } for e in sorted(s.events, key=lambda e: e.created_at or 0)],
    }
    if private:
        data.update({
            "customer": s.customer.company, "customer_id": s.customer_id,
            "amount": s.amount, "currency": s.currency, "payment_term": s.payment_term.value, "paid": s.paid,
            "suppliers": [supplier_dict(x) for x in s.suppliers], "totals": totals(s.suppliers),
            "documents": [{"id": d.id, "name": d.name, "kind": d.kind, "status": d.status.value, "note": d.note} for d in s.documents],
        })
    return data


@app.post("/api/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is wrong")
    return {"token": f"user:{user.id}", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value, "customer_id": user.customer_id}}


@app.get("/api/me")
def me(user: User = Depends(require_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value, "customer_id": user.customer_id}


@app.get("/api/chat/config")
def chat_config():
    base = os.environ.get("CHATWOOT_BASE_URL", "")
    token = os.environ.get("CHATWOOT_WEBSITE_TOKEN", "")
    return {"enabled": bool(base and token), "base_url": base, "website_token": token}


@app.get("/api/meta")
def meta():
    return {
        "statuses": STATUSES,
        "load_types": [x.value for x in LoadType],
        "payment_terms": [x.value for x in PaymentTerm],
        "doc_statuses": [x.value for x in DocStatus],
        "service_types": ["Door-to-Door", "Warehouse-to-Warehouse", "Port-to-Port", "Warehouse at Destination"],
    }


@app.get("/api/customers")
def customers(user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.query(Customer).filter(Customer.id == user.customer_id).all() if user.role == Role.customer else db.query(Customer).order_by(Customer.company).all()
    return [{"id": c.id, "company": c.company, "contact_name": c.contact_name, "email": c.email, "phone": c.phone, "country": c.country} for c in rows]


@app.get("/api/rfqs")
def list_rfqs(user: User = Depends(require_user), db: Session = Depends(get_db)):
    q = db.query(RFQ).options(joinedload(RFQ.customer), joinedload(RFQ.suppliers).joinedload(RFQSupplier.products), joinedload(RFQ.quotes))
    if user.role == Role.customer:
        q = q.filter(RFQ.customer_id == user.customer_id)
    return [rfq_dict(r) for r in q.order_by(RFQ.id.desc()).all()]


@app.post("/api/rfqs")
def create_rfq(body: RFQIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.customer or not user.customer_id:
        raise HTTPException(403, "Only a customer can raise an RFQ")
    if not body.suppliers:
        raise HTTPException(400, "Add at least one supplier")
    rfq = RFQ(reference=new_ref("RFQ"), customer_id=user.customer_id, origin=body.origin, destination=body.destination, load_type=body.load_type, service_type=body.service_type, notes=body.notes, status=RFQStatus.submitted)
    db.add(rfq)
    db.flush()
    for s in body.suppliers:
        sup = RFQSupplier(rfq_id=rfq.id, name=s.name, code=s.code, city=s.city)
        db.add(sup)
        db.flush()
        for p in s.products:
            db.add(RFQProduct(supplier_id=sup.id, **p.model_dump()))
    db.commit()
    db.refresh(rfq)
    return rfq_dict(rfq)


@app.post("/api/rfqs/{rfq_id}/quote")
def quote_rfq(rfq_id: int, body: QuoteIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    db.add(Quote(reference=new_ref("QTE"), rfq_id=rfq.id, created_by=user.id, status=QuoteStatus.sent, **body.model_dump()))
    rfq.status = RFQStatus.quoted
    db.commit()
    db.refresh(rfq)
    return rfq_dict(rfq)


@app.post("/api/quotes/{quote_id}/accept")
def accept_quote(quote_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    rfq = db.query(RFQ).options(joinedload(RFQ.suppliers).joinedload(RFQSupplier.products)).filter(RFQ.id == quote.rfq_id).first()
    if user.role == Role.customer and user.customer_id != rfq.customer_id:
        raise HTTPException(403, "Not your quote")
    if quote.status == QuoteStatus.accepted:
        raise HTTPException(400, "Already accepted")
    quote.status = QuoteStatus.accepted
    rfq.status = RFQStatus.accepted
    ship = Shipment(reference=new_ref("SHP"), public_token=new_ref("trk").lower(), customer_id=rfq.customer_id, rfq_id=rfq.id, quote_id=quote.id, origin=quote.origin, destination=quote.destination, load_type=rfq.load_type, service_type=quote.service_type, source="rfq", status=STATUSES[0], payment_term=quote.payment_term, amount=quote.amount, currency=quote.currency)
    db.add(ship)
    db.flush()
    for s in rfq.suppliers:
        ss = ShipmentSupplier(shipment_id=ship.id, name=s.name, code=s.code)
        db.add(ss)
        db.flush()
        for p in s.products:
            db.add(ShipmentProduct(supplier_id=ss.id, name=p.name, description=p.description, hs_code=p.hs_code, quantity=p.quantity, unit=p.unit, unit_price=p.unit_price, weight_kg=p.weight_kg, cbm=p.cbm))
    db.add(StatusEvent(shipment_id=ship.id, status=STATUSES[0], note="Created from accepted quote", actor=user.name))
    for name, kind in [("Commercial Invoice", "invoice"), ("Packing List", "packing_list"), ("KYC", "kyc")]:
        db.add(Document(shipment_id=ship.id, name=name, kind=kind, status=DocStatus.required))
    db.commit()
    return {"shipment_reference": ship.reference, "public_token": ship.public_token}


@app.get("/api/shipments")
def list_shipments(user: User = Depends(require_user), db: Session = Depends(get_db)):
    q = db.query(Shipment).options(joinedload(Shipment.customer), joinedload(Shipment.suppliers).joinedload(ShipmentSupplier.products), joinedload(Shipment.events), joinedload(Shipment.documents))
    if user.role == Role.customer:
        q = q.filter(Shipment.customer_id == user.customer_id)
    return [shipment_dict(s, True) for s in q.order_by(Shipment.id.desc()).all()]


@app.post("/api/shipments")
def direct_shipment(body: DirectShipmentIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    if body.customer_id:
        customer = db.get(Customer, body.customer_id)
        if not customer:
            raise HTTPException(404, "Customer not found")
    else:
        if not body.company or not body.email:
            raise HTTPException(400, "Company and email are required for a new customer")
        customer = Customer(company=body.company, contact_name=body.contact_name or body.company, email=body.email, phone=body.phone)
        db.add(customer)
        db.flush()
        db.add(User(name=customer.contact_name, email=body.email, password_hash=hash_password("customer123"), role=Role.customer, customer_id=customer.id))
    ship = Shipment(reference=new_ref("SHP"), public_token=new_ref("trk").lower(), customer_id=customer.id, origin=body.origin, destination=body.destination, load_type=body.load_type, service_type=body.service_type, source="direct", status=STATUSES[0], payment_term=body.payment_term, amount=body.amount, currency=body.currency)
    db.add(ship)
    db.flush()
    for s in body.suppliers:
        ss = ShipmentSupplier(shipment_id=ship.id, name=s.name, code=s.code)
        db.add(ss)
        db.flush()
        for p in s.products:
            db.add(ShipmentProduct(supplier_id=ss.id, name=p.name, description=p.description, hs_code=p.hs_code, quantity=p.quantity, unit=p.unit, unit_price=p.unit_price, weight_kg=p.weight_kg, cbm=p.cbm))
    db.add(StatusEvent(shipment_id=ship.id, status=STATUSES[0], note="Direct shipment opened by ops", actor=user.name))
    db.commit()
    return {"reference": ship.reference, "public_token": ship.public_token, "customer_id": customer.id}


@app.post("/api/shipments/{shipment_id}/status")
def update_status(shipment_id: int, body: StatusIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    if body.status not in STATUSES:
        raise HTTPException(400, "Unknown status")
    ship = db.get(Shipment, shipment_id)
    if not ship:
        raise HTTPException(404, "Shipment not found")
    ship.status = body.status
    db.add(StatusEvent(shipment_id=ship.id, status=body.status, note=body.note, actor=user.name))
    db.commit()
    return {"ok": True, "status": ship.status}


@app.post("/api/shipments/{shipment_id}/documents")
def add_document(shipment_id: int, body: DocIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    if not db.get(Shipment, shipment_id):
        raise HTTPException(404, "Shipment not found")
    doc = Document(shipment_id=shipment_id, name=body.name, kind=body.kind, status=body.status)
    db.add(doc)
    db.commit()
    return {"id": doc.id}


@app.get("/api/track/{token}")
def public_track(token: str, db: Session = Depends(get_db)):
    ship = db.query(Shipment).options(joinedload(Shipment.events)).filter(Shipment.public_token == token).first()
    if not ship:
        raise HTTPException(404, "Tracking number not found")
    return shipment_dict(ship, private=False)


@app.get("/api/dashboard")
def dashboard(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role not in (Role.admin, Role.manager_ops):
        raise HTTPException(403, "Master dashboard is for admin and manager ops")
    shipments = db.query(Shipment).all()
    rfqs = db.query(RFQ).all()
    return {
        "active_shipments": sum(1 for s in shipments if s.status != "Delivered"),
        "rfqs_pending": sum(1 for r in rfqs if r.status in (RFQStatus.submitted, RFQStatus.in_review)),
        "quotes_pending": sum(1 for r in rfqs if r.status == RFQStatus.quoted),
        "direct_shipments": sum(1 for s in shipments if s.source == "direct"),
        "in_transit": sum(1 for s in shipments if "Transit" in s.status or "Sailing" in s.status),
        "warehouse": sum(1 for s in shipments if "Warehouse" in s.status or "Inspection" in s.status),
        "customs_pending": sum(1 for s in shipments if s.status == "Pending Customs Clearance"),
        "delivered": sum(1 for s in shipments if s.status == "Delivered"),
    }


@app.get("/api/messages")
def messages(user: User = Depends(require_user), db: Session = Depends(get_db)):
    q = db.query(Message).filter(Message.channel == "support")
    if user.role == Role.customer:
        q = q.filter(Message.customer_id == user.customer_id)
    return [{
        "id": m.id, "author": m.author, "role": m.role, "body": m.body,
        "customer_id": m.customer_id, "channel": m.channel,
        "at": m.created_at.isoformat() if m.created_at else None,
    } for m in q.order_by(Message.id).all()]


@app.post("/api/messages")
def post_message(body: MessageIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not body.body.strip():
        raise HTTPException(400, "Message is empty")
    if user.role == Role.customer:
        customer_id = user.customer_id
    else:
        customer_id = body.customer_id or (db.query(Customer).first().id if db.query(Customer).first() else None)
    if not customer_id:
        raise HTTPException(400, "No customer for this chat")
    msg = Message(customer_id=customer_id, author=user.name, role=user.role.value, channel="support", body=body.body.strip())
    db.add(msg)
    db.commit()
    return {"id": msg.id}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
