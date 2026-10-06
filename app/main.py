import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from .database import Base, engine, get_db
from .models import (
    STATUSES,
    Customer,
    CustomerNote,
    Document,
    DocStatus,
    LoadType,
    Message,
    Notice,
    PaymentTerm,
    ProductPhoto,
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
    SignupRequest,
    Setting,
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
        rfq_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(rfqs)").fetchall()]
        if rfq_cols and "assigned_to_id" not in rfq_cols:
            conn.exec_driver_sql("ALTER TABLE rfqs ADD COLUMN assigned_to_id INTEGER")
        doc_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(documents)").fetchall()]
        if doc_cols and "rfq_id" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN rfq_id INTEGER")
        if doc_cols and "file_name" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN file_name VARCHAR(255) DEFAULT ''")
        user_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if user_cols and "login_name" not in user_cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN login_name VARCHAR(80)")
        if user_cols and "last_seen" not in user_cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_seen DATETIME")
        if user_cols and "last_read_message_id" not in user_cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_read_message_id INTEGER DEFAULT 0")
        cust_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(customers)").fetchall()]
        if cust_cols and "address" not in cust_cols:
            conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN address TEXT DEFAULT ''")
        for col, ddl in [
            ("preferred_lane", "VARCHAR(180) DEFAULT ''"),
            ("preferred_load", "VARCHAR(20) DEFAULT 'LCL'"),
            ("payment_preference", "VARCHAR(40) DEFAULT 'pay_on_delivery'"),
            ("notes", "TEXT DEFAULT ''"),
        ]:
            if cust_cols and col not in cust_cols:
                conn.exec_driver_sql(f"ALTER TABLE customers ADD COLUMN {col} {ddl}")
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


class SignupIn(BaseModel):
    name: str
    login_name: str
    email: str
    phone: str
    address: str


class ReviewIn(BaseModel):
    password: str = "customer123"
    company: str = ""
    note: str = ""


class CustomerIn(BaseModel):
    company: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    country: str = ""
    preferred_lane: str = ""
    preferred_load: str = "LCL"
    payment_preference: str = "pay_on_delivery"
    notes: str = ""
    history_note: str = ""


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
        "photos": [{"id": photo.id, "file_name": photo.file_name} for photo in getattr(p, "photos", [])],
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
        "documents": [{"id": d.id, "name": d.name, "kind": d.kind, "status": d.status.value, "note": d.note, "file_name": d.file_name} for d in r.documents],
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
            "documents": [{"id": d.id, "name": d.name, "kind": d.kind, "status": d.status.value, "note": d.note, "file_name": d.file_name} for d in s.documents],
        })
    return data


@app.post("/api/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    key = body.email.strip().lower()
    user = db.query(User).filter((User.email == key) | (User.login_name == key)).first()
    if not user or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is wrong")
    return {"token": f"user:{user.id}", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value, "customer_id": user.customer_id, "login_name": user.login_name}}


@app.get("/api/me")
def me(user: User = Depends(require_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value, "customer_id": user.customer_id}


@app.get("/api/chat/config")
def chat_config():
    raw = os.environ.get("TAWK_PROPERTY_ID", "").strip().rstrip("/")
    widget_id = os.environ.get("TAWK_WIDGET_ID", "").strip()
    if "embed.tawk.to/" in raw:
        raw = raw.split("embed.tawk.to/", 1)[1]
    if "/" in raw:
        property_id, embedded_widget = raw.split("/", 1)
        widget_id = widget_id or embedded_widget
    else:
        property_id = raw
    return {
        "provider": "tawk" if property_id and widget_id else "missing",
        "enabled": bool(property_id and widget_id),
        "property_id": property_id,
        "widget_id": widget_id,
    }


@app.get("/api/meta")
def meta():
    return {
        "statuses": STATUSES,
        "load_types": [x.value for x in LoadType],
        "payment_terms": [x.value for x in PaymentTerm],
        "doc_statuses": [x.value for x in DocStatus],
        "service_types": ["Door-to-Door", "Warehouse-to-Warehouse", "Port-to-Port", "Warehouse at Destination"],
    }


@app.post("/api/registrations")
def register(body: SignupIn, db: Session = Depends(get_db)):
    login_name = body.login_name.strip().lower()
    email = body.email.strip().lower()
    if not all([body.name.strip(), login_name, email, body.phone.strip(), body.address.strip()]):
        raise HTTPException(400, "Name, login name, email, phone, and address are required")
    if db.query(User).filter((User.email == email) | (User.login_name == login_name)).first():
        raise HTTPException(400, "That login name or email is already in use")
    if db.query(SignupRequest).filter(SignupRequest.status == "pending", (SignupRequest.email == email) | (SignupRequest.login_name == login_name)).first():
        raise HTTPException(400, "A request for this login is already waiting for ops")
    row = SignupRequest(name=body.name.strip(), login_name=login_name, email=email, phone=body.phone.strip(), address=body.address.strip())
    db.add(row)
    db.commit()
    return {"id": row.id, "status": "pending"}


@app.get("/api/registrations")
def list_registrations(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    return [{
        "id": r.id, "name": r.name, "login_name": r.login_name, "email": r.email,
        "phone": r.phone, "address": r.address, "status": r.status, "note": r.note,
    } for r in db.query(SignupRequest).order_by(SignupRequest.id.desc()).all()]


@app.post("/api/registrations/{request_id}/approve")
def approve_registration(request_id: int, body: ReviewIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    row = db.get(SignupRequest, request_id)
    if not row or row.status != "pending":
        raise HTTPException(404, "Pending request not found")
    customer = Customer(company=body.company.strip() or row.name, contact_name=row.name, email=row.email, phone=row.phone, address=row.address)
    db.add(customer)
    db.flush()
    db.add(User(name=row.name, email=row.email, login_name=row.login_name, password_hash=hash_password(body.password or "customer123"), role=Role.customer, customer_id=customer.id))
    row.status = "approved"
    row.note = body.note or f"Approved by {user.name}"
    db.commit()
    return {"ok": True, "login_name": row.login_name, "password": body.password or "customer123"}


@app.post("/api/registrations/{request_id}/reject")
def reject_registration(request_id: int, body: ReviewIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    row = db.get(SignupRequest, request_id)
    if not row or row.status != "pending":
        raise HTTPException(404, "Pending request not found")
    row.status = "rejected"
    row.note = body.note or f"Rejected by {user.name}"
    db.commit()
    return {"ok": True}


@app.get("/api/customers")
def customers(user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.query(Customer).filter(Customer.id == user.customer_id).all() if user.role == Role.customer else db.query(Customer).order_by(Customer.company).all()
    return [{
        "id": c.id, "company": c.company, "contact_name": c.contact_name, "email": c.email,
        "phone": c.phone, "address": c.address, "country": c.country,
        "preferred_lane": c.preferred_lane, "preferred_load": c.preferred_load,
        "payment_preference": c.payment_preference, "notes": c.notes,
        "orders": len(c.shipments), "rfqs": len(c.rfqs),
    } for c in rows]


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer and user.customer_id != customer_id:
        raise HTTPException(403, "Not your account")
    c = db.query(Customer).options(joinedload(Customer.rfqs), joinedload(Customer.shipments), joinedload(Customer.history)).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(404, "Customer not found")
    messages = db.query(Message).filter(Message.customer_id == c.id).order_by(Message.id.desc()).limit(8).all()
    return {
        "id": c.id, "company": c.company, "contact_name": c.contact_name, "email": c.email,
        "phone": c.phone, "address": c.address, "country": c.country,
        "preferred_lane": c.preferred_lane, "preferred_load": c.preferred_load,
        "payment_preference": c.payment_preference, "notes": c.notes,
        "rfqs": [{"id": r.id, "reference": r.reference, "origin": r.origin, "destination": r.destination, "status": r.status.value} for r in c.rfqs],
        "orders": [{"id": s.id, "reference": s.reference, "origin": s.origin, "destination": s.destination, "status": s.status, "amount": s.amount, "currency": s.currency} for s in c.shipments],
        "history": [{"author": n.author, "body": n.body, "at": n.created_at.isoformat() if n.created_at else None} for n in c.history],
        "messages": [{"author": m.author, "body": m.body} for m in messages],
    }


@app.patch("/api/customers/{customer_id}")
def update_customer(customer_id: int, body: CustomerIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer and user.customer_id != customer_id:
        raise HTTPException(403, "Not your account")
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "Customer not found")
    fields = ["company", "contact_name", "email", "phone", "address", "country", "preferred_lane", "preferred_load", "payment_preference"]
    if user.role != Role.customer:
        fields.append("notes")
    for key in fields:
        setattr(c, key, getattr(body, key))
    if user.role != Role.customer and body.history_note.strip():
        db.add(CustomerNote(customer_id=c.id, author=user.name, body=body.history_note.strip()))
    db.commit()
    return {"ok": True}


@app.get("/api/queue")
def ops_queue(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    staff = db.query(User).filter(User.role != Role.customer).all()
    accounts = db.query(SignupRequest).filter(SignupRequest.status == "pending").all()
    rfqs = db.query(RFQ).options(joinedload(RFQ.customer), joinedload(RFQ.documents), joinedload(RFQ.quotes)).all()
    items = []
    for row in accounts:
        items.append({"kind": "account", "id": row.id, "title": row.name, "detail": f"{row.login_name} · {row.email}", "action": "Approve account"})
    for rfq in rfqs:
        if rfq.status in (RFQStatus.submitted, RFQStatus.in_review):
            items.append({"kind": "rfq", "id": rfq.id, "title": rfq.reference, "detail": f"{rfq.customer.company} · {rfq.origin} → {rfq.destination}", "action": "Quote needed", "assigned_to_id": rfq.assigned_to_id})
        for quote in rfq.quotes:
            if quote.status == QuoteStatus.sent:
                items.append({"kind": "quote", "id": rfq.id, "title": quote.reference, "detail": f"{rfq.reference} waiting for customer", "action": "Quote pending"})
        for doc in rfq.documents:
            if doc.status == DocStatus.required:
                items.append({"kind": "document", "id": rfq.id, "title": doc.name, "detail": f"Missing on {rfq.reference}", "action": "Ask customer"})
    return {"count": len(items), "items": items, "staff": [{"id": u.id, "name": u.name} for u in staff]}


@app.post("/api/rfqs/{rfq_id}/assign")
def assign_rfq(rfq_id: int, user_id: int = Query(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    rfq.assigned_to_id = user_id
    db.commit()
    return {"ok": True}


@app.get("/api/quotes/{quote_id}/download")
def download_quote(quote_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    rfq = db.query(RFQ).options(joinedload(RFQ.customer)).filter(RFQ.id == quote.rfq_id).first()
    if user.role == Role.customer and user.customer_id != rfq.customer_id:
        raise HTTPException(403, "Not your quote")
    html = f"""<html><body><h1>Trackzy quote {quote.reference}</h1>
    <p>{rfq.customer.company}<br>{quote.origin} to {quote.destination}</p>
    <p><strong>{quote.currency} {quote.amount}</strong> · {quote.service_type} · {quote.payment_term.value}</p>
    <p>Transit: {quote.transit}</p><p>Included: {quote.included}</p><p>Excluded: {quote.excluded}</p>
    <p>Documents: {quote.documents_required}</p><p>{quote.instructions}</p></body></html>"""
    return HTMLResponse(html, headers={"Content-Disposition": f"attachment; filename={quote.reference}.html"})


@app.get("/api/rfqs")
def list_rfqs(user: User = Depends(require_user), db: Session = Depends(get_db)):
    q = db.query(RFQ).options(joinedload(RFQ.customer), joinedload(RFQ.suppliers).joinedload(RFQSupplier.products), joinedload(RFQ.quotes), joinedload(RFQ.documents))
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


UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)


@app.post("/api/rfqs/{rfq_id}/documents")
async def upload_rfq_document(rfq_id: int, kind: str = Query("invoice"), file: UploadFile = File(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq or (user.role == Role.customer and user.customer_id != rfq.customer_id):
        raise HTTPException(404, "RFQ not found")
    label = "Commercial Invoice" if kind == "invoice" else "Packing List" if kind == "packing_list" else file.filename
    stored = f"{rfq.reference}-{kind}-{file.filename}".replace(" ", "_")
    (UPLOADS / stored).write_bytes(await file.read())
    existing = db.query(Document).filter(Document.rfq_id == rfq.id, Document.kind == kind, Document.status == DocStatus.required).first()
    if existing:
        existing.status = DocStatus.uploaded
        existing.file_name = stored
        existing.note = f"Uploaded by {user.name}"
        row = existing
    else:
        row = Document(rfq_id=rfq.id, name=label, kind=kind, status=DocStatus.uploaded, file_name=stored, note=f"Uploaded by {user.name}")
        db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "status": row.status.value}


@app.post("/api/rfqs/{rfq_id}/documents/request")
def request_rfq_document(rfq_id: int, kind: str = Query("invoice"), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    label = "Commercial Invoice" if kind == "invoice" else "Packing List"
    db.add(Document(rfq_id=rfq.id, name=label, kind=kind, status=DocStatus.required, note=f"Requested by {user.name}"))
    db.add(Message(customer_id=rfq.customer_id, author=user.name, role=user.role.value, channel="support", body=f"Please upload the {label} for {rfq.reference}."))
    db.commit()
    return {"ok": True}


@app.get("/api/documents/{document_id}")
def download_document(document_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or not doc.file_name or not (UPLOADS / doc.file_name).exists():
        raise HTTPException(404, "File not uploaded")
    if user.role == Role.customer:
        owner = None
        if doc.rfq_id:
            owner = db.get(RFQ, doc.rfq_id)
        elif doc.shipment_id:
            owner = db.get(Shipment, doc.shipment_id)
        if not owner or owner.customer_id != user.customer_id:
            raise HTTPException(403, "Not your document")
    return FileResponse(UPLOADS / doc.file_name, filename=doc.file_name)


@app.post("/api/products/{product_id}/photos")
async def upload_product_photo(product_id: int, file: UploadFile = File(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    product = db.get(RFQProduct, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    stored = f"product-{product_id}-{file.filename}".replace(" ", "_")
    (UPLOADS / stored).write_bytes(await file.read())
    photo = ProductPhoto(product_id=product.id, file_name=stored)
    db.add(photo)
    db.commit()
    return {"id": photo.id}


@app.get("/api/photos/{photo_id}")
def download_photo(photo_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    photo = db.get(ProductPhoto, photo_id)
    if not photo or not (UPLOADS / photo.file_name).exists():
        raise HTTPException(404, "Photo not found")
    return FileResponse(UPLOADS / photo.file_name)


@app.patch("/api/documents/{document_id}")
def update_document(document_id: int, status: str = Query(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    doc = db.get(Document, document_id)
    if not doc or status not in {item.value for item in DocStatus}:
        raise HTTPException(404, "Document not found")
    doc.status = DocStatus(status)
    doc.note = f"Marked {status} by {user.name}"
    db.commit()
    return {"id": doc.id, "status": doc.status.value}


@app.get("/api/notices")
def notices(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.customer or not user.customer_id:
        return []
    rows = db.query(Notice).filter(Notice.customer_id == user.customer_id).order_by(Notice.id.desc()).all()
    return [{"id": n.id, "title": n.title, "body": n.body, "read": n.read} for n in rows]


@app.post("/api/notices/{notice_id}/read")
def read_notice(notice_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    notice = db.get(Notice, notice_id)
    if not notice or notice.customer_id != user.customer_id:
        raise HTTPException(404, "Notice not found")
    notice.read = True
    db.commit()
    return {"ok": True}


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


@app.patch("/api/quotes/{quote_id}")
def edit_quote(quote_id: int, body: QuoteIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role == Role.customer:
        raise HTTPException(403, "Ops only")
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    if quote.status == QuoteStatus.accepted:
        raise HTTPException(400, "Accepted quote cannot be edited")
    for key, value in body.model_dump().items():
        setattr(quote, key, value)
    quote.status = QuoteStatus.sent
    db.commit()
    return {"id": quote.id, "amount": quote.amount, "included": quote.included, "transit": quote.transit}


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
    db.add(Notice(customer_id=customer.id, title=f"Shipment {ship.reference} opened", body=f"Ops opened a shipment from {ship.origin} to {ship.destination}. Tracking /?track={ship.public_token}"))
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
    key = token.strip()
    ship = db.query(Shipment).options(joinedload(Shipment.events)).filter(
        (Shipment.public_token == key) | (Shipment.reference == key)
    ).first()
    if not ship:
        raise HTTPException(404, "Tracking number not found")
    return shipment_dict(ship, private=False)


@app.get("/api/dashboard")
def dashboard(q: str = "", user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role not in (Role.admin, Role.manager_ops):
        raise HTTPException(403, "Master dashboard is for admin and manager ops")
    shipments = db.query(Shipment).options(joinedload(Shipment.customer)).all()
    rfqs = db.query(RFQ).options(joinedload(RFQ.customer)).all()
    docs = db.query(Document).all()
    staff = db.query(User).filter(User.role != Role.customer).all()
    now = datetime.utcnow()
    delayed = [s for s in shipments if s.status != "Delivered" and s.created_at and (now - s.created_at).days >= 14]
    stale_rfq = [r for r in rfqs if r.status in (RFQStatus.submitted, RFQStatus.in_review) and r.created_at and (now - r.created_at).days >= 2]
    alerts = [f"{s.reference} is still {s.status} after 14 days" for s in delayed]
    alerts += [f"{r.reference} has had no quote for 2 days" for r in stale_rfq]
    alerts += [f"{d.name} is {d.status.value}" for d in docs if d.status in (DocStatus.missing, DocStatus.rejected)]
    needle = q.strip().lower()
    matches = []
    if needle:
        matches = [{"kind": "shipment", "label": f"{s.reference} · {s.customer.company}"} for s in shipments if needle in s.reference.lower() or needle in s.customer.company.lower()]
        matches += [{"kind": "rfq", "label": f"{r.reference} · {r.customer.company}"} for r in rfqs if needle in r.reference.lower() or needle in r.customer.company.lower()]
    return {
        "active_shipments": sum(1 for s in shipments if s.status != "Delivered"),
        "rfqs_pending": sum(1 for r in rfqs if r.status in (RFQStatus.submitted, RFQStatus.in_review)),
        "quotes_pending": sum(1 for r in rfqs if r.status == RFQStatus.quoted),
        "direct_shipments": sum(1 for s in shipments if s.source == "direct"),
        "in_transit": sum(1 for s in shipments if "Transit" in s.status or "Sailing" in s.status),
        "warehouse": sum(1 for s in shipments if "Warehouse" in s.status or "Inspection" in s.status),
        "customs_pending": sum(1 for s in shipments if s.status == "Pending Customs Clearance"),
        "delivered": sum(1 for s in shipments if s.status == "Delivered"),
        "documents_pending": sum(1 for d in docs if d.status in (DocStatus.required, DocStatus.missing, DocStatus.rejected)),
        "delayed": len(delayed),
        "workload": [{"name": u.name, "assigned": sum(1 for r in rfqs if r.assigned_to_id == u.id)} for u in staff],
        "alerts": alerts,
        "search": matches,
    }


@app.get("/api/users")
def list_users(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    return [{"id": u.id, "name": u.name, "email": u.email, "login_name": u.login_name, "role": u.role.value} for u in db.query(User).all()]


class UserIn(BaseModel):
    name: str
    email: str
    login_name: str = ""
    password: str = "ops123"
    role: str = "ops"


@app.post("/api/users")
def create_user(body: UserIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    if body.role not in {item.value for item in Role}:
        raise HTTPException(400, "Unknown role")
    row = User(name=body.name, email=body.email.strip().lower(), login_name=body.login_name.strip().lower() or None, password_hash=hash_password(body.password), role=Role(body.role))
    db.add(row)
    db.commit()
    return {"id": row.id}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, role: str = Query(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    row = db.get(User, user_id)
    if not row or role not in {item.value for item in Role}:
        raise HTTPException(404, "User not found")
    row.role = Role(role)
    db.commit()
    return {"ok": True}


@app.get("/api/settings")
def get_settings(user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    row = db.get(Setting, "support_mode")
    return {"support_mode": row.value if row else "ops"}


@app.patch("/api/settings")
def save_settings(support_mode: str = Query("ops"), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only")
    if support_mode not in {"ops", "support", "hybrid"}:
        raise HTTPException(400, "Unknown support mode")
    row = db.get(Setting, "support_mode") or Setting(key="support_mode")
    row.value = support_mode
    db.merge(row)
    db.commit()
    return {"support_mode": support_mode}


@app.get("/api/messages")
def messages(user: User = Depends(require_user), db: Session = Depends(get_db)):
    q = db.query(Message).filter(Message.channel == "support")
    if user.role == Role.customer:
        q = q.filter(Message.customer_id == user.customer_id)
    customers = db.query(Customer).filter(Customer.id == user.customer_id).all() if user.role == Role.customer else db.query(Customer).order_by(Customer.company).all()
    names = {c.id: c.company for c in customers}
    return {
        "customers": [{"id": c.id, "company": c.company, "email": c.email} for c in customers],
        "messages": [{
            "id": m.id, "author": m.author, "role": m.role, "body": m.body,
            "customer_id": m.customer_id, "customer": names.get(m.customer_id, "Customer"),
            "at": m.created_at.isoformat() if m.created_at else None,
        } for m in q.order_by(Message.id).all()],
    }


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


@app.post("/api/presence")
def presence(user: User = Depends(require_user), db: Session = Depends(get_db)):
    user.last_seen = datetime.utcnow()
    if user.role != Role.customer:
        latest = db.query(Message).order_by(Message.id.desc()).first()
        user.last_read_message_id = latest.id if latest and user.last_read_message_id and False else user.last_read_message_id
    db.commit()
    cutoff = datetime.utcnow() - timedelta(seconds=45)
    staff = db.query(User).filter(User.role.in_([Role.ops, Role.support, Role.manager_ops, Role.admin]), User.last_seen != None, User.last_seen >= cutoff).all()
    unread = 0
    if user.role != Role.customer:
        unread = db.query(Message).filter(Message.role == "customer", Message.id > (user.last_read_message_id or 0)).count()
    return {
        "online": [{"name": u.name, "role": u.role.value} for u in staff],
        "unread": unread,
    }


@app.post("/api/messages/read")
def mark_read(user: User = Depends(require_user), db: Session = Depends(get_db)):
    latest = db.query(Message).order_by(Message.id.desc()).first()
    user.last_read_message_id = latest.id if latest else 0
    user.last_seen = datetime.utcnow()
    db.commit()
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
