# Trackzy

Logistics arm of Sourceeasy. This is the first build: our own schema, not a fork of Fleetbase or Twenty.

## Run

```bash
cd trackzy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Docker on the VPS

Trackzy and PostgreSQL run as two containers. The site is `https://trackzy.in`. Point the DNS A record at the VPS, then:

```bash
cd trackzy
cp .env.example .env
# set POSTGRES_PASSWORD
docker compose up -d --build
```

If the VPS already has Nginx or Caddy on ports 80 and 443, do not publish 8000 publicly. Use `deploy/trackzy.in.nginx.conf` to proxy `trackzy.in` to `127.0.0.1:8000`, then add a certificate with certbot. The app container talks to Postgres on the compose network as `db`. Postgres is not exposed to the internet.

## Chat

Customer chat is the Tawk.to bubble on `trackzy.in`. Agents reply in the Tawk.to dashboard. The widget id is `1k46v5qfs`.

## Demo logins

| Role | Email | Password |
|---|---|---|
| Customer | customer@trackzy.test | customer123 |
| Ops | ops@trackzy.test | ops123 |
| Support | support@trackzy.test | support123 |
| Manager ops | manager@trackzy.test | manager123 |
| Admin | admin@trackzy.test | admin123 |

Public tracking sample: http://127.0.0.1:8000/?track=trk_8f3a21

## What this slice does

- Customer RFQ with supplier and product lines, weight, CBM, and value
- Ops manual quote, pay on delivery by default
- Accept quote creates a shipment and a public token
- Ops can open a direct shipment for an existing or new customer
- Ops advances the status timeline
- Public page shows reference, lane, and timeline only
- Signed-in customer sees suppliers, products, and documents
- Master counts for admin and manager ops

Not in this slice yet: file upload, ads, SSO with Sourceeasy, native apps.
