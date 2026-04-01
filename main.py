import os
import sqlite3
import smtplib
import ssl
import json
from datetime import datetime, date, timedelta
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Invoice Nudge", description="Freelancer invoice tracker with automated reminder sequences")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "./invoicenudge.db")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "invoices@yourcompany.com")
FROM_NAME = os.getenv("FROM_NAME", "Your Company")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Your Company")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "123 Main St, City, State")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                company TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                invoice_number TEXT NOT NULL UNIQUE,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                description TEXT,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                sent_at TEXT,
                paid_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT (datetime('now')),
                email_subject TEXT,
                email_body TEXT,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            );
        """)


def seed_data():
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        if existing > 0:
            return

        now = datetime.utcnow()
        today = date.today()

        conn.execute(
            "INSERT INTO clients (name, email, company, created_at) VALUES (?, ?, ?, ?)",
            ("Alice Johnson", "alice@acmecorp.com", "Acme Corp", now.isoformat())
        )
        conn.execute(
            "INSERT INTO clients (name, email, company, created_at) VALUES (?, ?, ?, ?)",
            ("Bob Martinez", "bob@techstart.io", "TechStart IO", now.isoformat())
        )
        conn.execute(
            "INSERT INTO clients (name, email, company, created_at) VALUES (?, ?, ?, ?)",
            ("Carol White", "carol@designstudio.com", "Design Studio", now.isoformat())
        )

        clients = conn.execute("SELECT id FROM clients ORDER BY id").fetchall()
        c1, c2, c3 = clients[0]["id"], clients[1]["id"], clients[2]["id"]

        invoices = [
            (c1, "INV-001", 2500.00, "USD", "Website redesign - Phase 1",
             (today - timedelta(days=45)).isoformat(), "paid",
             (now - timedelta(days=50)).isoformat(), (now - timedelta(days=30)).isoformat()),
            (c2, "INV-002", 1800.00, "USD", "Mobile app UI design",
             (today - timedelta(days=20)).isoformat(), "overdue",
             (now - timedelta(days=35)).isoformat(), None),
            (c3, "INV-003", 950.00, "USD", "Brand identity package",
             (today - timedelta(days=10)).isoformat(), "overdue",
             (now - timedelta(days=25)).isoformat(), None),
            (c1, "INV-004", 3200.00, "USD", "SEO consulting - Q1 2026",
             (today + timedelta(days=15)).isoformat(), "sent",
             (now - timedelta(days=5)).isoformat(), None),
            (c2, "INV-005", 600.00, "USD", "Logo design revisions",
             (today + timedelta(days=30)).isoformat(), "draft", None, None),
        ]

        for inv in invoices:
            conn.execute(
                """INSERT INTO invoices
                   (client_id, invoice_number, amount, currency, description, due_date, status, sent_at, paid_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*inv, now.isoformat())
            )


@app.on_event("startup")
async def startup_event():
    create_tables()
    seed_data()


# ── Email helpers ──────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body_html: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL SKIPPED] To: {to} | Subject: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg["To"] = to
        part = MIMEText(body_html, "html")
        msg.attach(part)
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def polite_reminder_template(invoice: dict, client: dict) -> tuple[str, str]:
    subject = f"Friendly Reminder: Invoice {invoice['invoice_number']} Due"
    days_overdue = invoice.get("days_overdue", 0)
    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
      <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
        <h2 style="color: #2c3e50;">Payment Reminder</h2>
        <p>Hi {client['name']},</p>
        <p>I hope this message finds you well! This is a friendly reminder that invoice
        <strong>{invoice['invoice_number']}</strong> for
        <strong>{invoice['currency']} {invoice['amount']:,.2f}</strong> was due on
        <strong>{invoice['due_date']}</strong> ({days_overdue} day(s) ago).</p>
        <div style="background: #fff; border-left: 4px solid #3498db; padding: 15px; margin: 20px 0;">
          <p style="margin:0;"><strong>Invoice:</strong> {invoice['invoice_number']}</p>
          <p style="margin:0;"><strong>Amount Due:</strong> {invoice['currency']} {invoice['amount']:,.2f}</p>
          <p style="margin:0;"><strong>Due Date:</strong> {invoice['due_date']}</p>
          <p style="margin:0;"><strong>Description:</strong> {invoice.get('description', '')}</p>
        </div>
        <p>If you've already sent the payment, please disregard this message. If you have any questions
        or need to discuss payment terms, I'm happy to chat.</p>
        <p>Thank you for your business!</p>
        <p>Best regards,<br><strong>{FROM_NAME}</strong><br>{COMPANY_NAME}<br>{COMPANY_ADDRESS}</p>
      </div>
    </body></html>
    """
    return subject, body


def firm_reminder_template(invoice: dict, client: dict) -> tuple[str, str]:
    subject = f"Important: Invoice {invoice['invoice_number']} Now {invoice.get('days_overdue', 0)} Days Overdue"
    days_overdue = invoice.get("days_overdue", 0)
    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
      <div style="background: #fff3cd; padding: 20px; border-radius: 8px; border: 1px solid #ffc107;">
        <h2 style="color: #856404;">Overdue Payment Notice</h2>
        <p>Hi {client['name']},</p>
        <p>I'm following up on invoice <strong>{invoice['invoice_number']}</strong> which is now
        <strong>{days_overdue} days overdue</strong>. The total amount of
        <strong>{invoice['currency']} {invoice['amount']:,.2f}</strong> was due on
        <strong>{invoice['due_date']}</strong>.</p>
        <div style="background: #fff; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
          <p style="margin:0;"><strong>Invoice:</strong> {invoice['invoice_number']}</p>
          <p style="margin:0;"><strong>Amount Due:</strong> {invoice['currency']} {invoice['amount']:,.2f}</p>
          <p style="margin:0;"><strong>Due Date:</strong> {invoice['due_date']}</p>
          <p style="margin:0;"><strong>Days Overdue:</strong> {days_overdue}</p>
          <p style="margin:0;"><strong>Description:</strong> {invoice.get('description', '')}</p>
        </div>
        <p>Please arrange payment at your earliest convenience. If there's an issue or you need a
        payment plan, please reach out immediately so we can work something out.</p>
        <p>Please treat this matter urgently.</p>
        <p>Regards,<br><strong>{FROM_NAME}</strong><br>{COMPANY_NAME}<br>{COMPANY_ADDRESS}</p>
      </div>
    </body></html>
    """
    return subject, body


def final_reminder_template(invoice: dict, client: dict) -> tuple[str, str]:
    subject = f"FINAL NOTICE: Invoice {invoice['invoice_number']} — Immediate Action Required"
    days_overdue = invoice.get("days_overdue", 0)
    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
      <div style="background: #f8d7da; padding: 20px; border-radius: 8px; border: 1px solid #dc3545;">
        <h2 style="color: #721c24;">FINAL NOTICE — Immediate Payment Required</h2>
        <p>Hi {client['name']},</p>
        <p>This is a <strong>final notice</strong> regarding invoice
        <strong>{invoice['invoice_number']}</strong>, which is now
        <strong>{days_overdue} days overdue</strong>. Despite previous reminders, we have not
        received payment of <strong>{invoice['currency']} {invoice['amount']:,.2f}</strong>
        which was due on <strong>{invoice['due_date']}</strong>.</p>
        <div style="background: #fff; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0;">
          <p style="margin:0;"><strong>Invoice:</strong> {invoice['invoice_number']}</p>
          <p style="margin:0;"><strong>Amount Due:</strong> {invoice['currency']} {invoice['amount']:,.2f}</p>
          <p style="margin:0;"><strong>Due Date:</strong> {invoice['due_date']}</p>
          <p style="margin:0;"><strong>Days Overdue:</strong> {days_overdue}</p>
          <p style="margin:0;"><strong>Description:</strong> {invoice.get('description', '')}</p>
        </div>
        <p><strong>Immediate payment is required.</strong> If payment is not received within 7 days,
        we will be forced to pursue further action including engaging a collections agency or
        initiating legal proceedings to recover the outstanding amount.</p>
        <p>To avoid further escalation, please make payment immediately and send a confirmation to
        this email address.</p>
        <p>Sincerely,<br><strong>{FROM_NAME}</strong><br>{COMPANY_NAME}<br>{COMPANY_ADDRESS}</p>
      </div>
    </body></html>
    """
    return subject, body


def invoice_sent_template(invoice: dict, client: dict) -> tuple[str, str]:
    subject = f"Invoice {invoice['invoice_number']} from {COMPANY_NAME}"
    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
      <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
        <h2 style="color: #2c3e50;">Invoice from {COMPANY_NAME}</h2>
        <p>Hi {client['name']},</p>
        <p>Please find below the details for invoice <strong>{invoice['invoice_number']}</strong>.
        Payment is due by <strong>{invoice['due_date']}</strong>.</p>
        <div style="background: #fff; border-left: 4px solid #27ae60; padding: 15px; margin: 20px 0;">
          <p style="margin:0;"><strong>Invoice Number:</strong> {invoice['invoice_number']}</p>
          <p style="margin:0;"><strong>Amount:</strong> {invoice['currency']} {invoice['amount']:,.2f}</p>
          <p style="margin:0;"><strong>Due Date:</strong> {invoice['due_date']}</p>
          <p style="margin:0;"><strong>Description:</strong> {invoice.get('description', '')}</p>
        </div>
        <p>Please process payment by the due date. If you have any questions, don't hesitate to reach out.</p>
        <p>Thank you for your business!</p>
        <p>Best regards,<br><strong>{FROM_NAME}</strong><br>{COMPANY_NAME}<br>{COMPANY_ADDRESS}</p>
      </div>
    </body></html>
    """
    return subject, body


# ── Pydantic models ────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    email: str
    company: Optional[str] = None


class InvoiceCreate(BaseModel):
    client_id: int
    invoice_number: str
    amount: float
    currency: str = "USD"
    description: Optional[str] = None
    due_date: str


class StatusUpdate(BaseModel):
    status: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def calc_days_overdue(due_date_str: str, status: str) -> int:
    if status in ("paid", "cancelled", "draft"):
        return 0
    try:
        due = date.fromisoformat(due_date_str)
        delta = (date.today() - due).days
        return max(0, delta)
    except Exception:
        return 0


def enrich_invoice(row: sqlite3.Row) -> dict:
    inv = dict(row)
    inv["days_overdue"] = calc_days_overdue(inv["due_date"], inv["status"])
    return inv


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with get_db() as conn:
        invoices = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            ORDER BY i.created_at DESC
        """).fetchall()
        invoices = [enrich_invoice(r) for r in invoices]

        stats_row = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN status NOT IN ('paid','cancelled') THEN amount ELSE 0 END),0) as total_outstanding,
              COALESCE(SUM(CASE WHEN status='overdue' THEN amount ELSE 0 END),0) as overdue_amount,
              COALESCE(SUM(CASE WHEN status='paid' AND strftime('%Y-%m', paid_at) = strftime('%Y-%m','now') THEN amount ELSE 0 END),0) as paid_this_month
            FROM invoices
        """).fetchone()

    total_outstanding = stats_row["total_outstanding"]
    overdue_amount = stats_row["overdue_amount"]
    paid_this_month = stats_row["paid_this_month"]

    def status_badge(status):
        colors = {
            "paid": ("28a745", "white"),
            "overdue": ("dc3545", "white"),
            "sent": ("ffc107", "212529"),
            "draft": ("6c757d", "white"),
            "cancelled": ("343a40", "white"),
        }
        bg, fg = colors.get(status, ("6c757d", "white"))
        return f'<span style="background:#{bg};color:#{fg};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{status.upper()}</span>'

    rows = ""
    for inv in invoices:
        overdue_text = f'<span style="color:#dc3545;font-size:12px;">{inv["days_overdue"]}d overdue</span>' if inv["days_overdue"] > 0 else ""
        rows += f"""
        <tr>
          <td style="padding:12px 8px;">{inv['invoice_number']}</td>
          <td style="padding:12px 8px;">{inv['client_name']}<br><small style="color:#6c757d;">{inv.get('company','')}</small></td>
          <td style="padding:12px 8px;">{inv['currency']} {inv['amount']:,.2f}</td>
          <td style="padding:12px 8px;">{inv['due_date']}<br>{overdue_text}</td>
          <td style="padding:12px 8px;">{status_badge(inv['status'])}</td>
          <td style="padding:12px 8px;">
            <div style="display:flex;gap:4px;flex-wrap:wrap;">
              {"" if inv['status'] != 'draft' else f'<button onclick="apiPost(\'/api/invoices/{inv["id"]}/send\')" style="background:#17a2b8;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;">Send</button>'}
              {"" if inv['status'] not in ('sent','overdue') else f'<button onclick="apiPost(\'/api/invoices/{inv["id"]}/remind\')" style="background:#fd7e14;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;">Remind</button>'}
              {"" if inv['status'] in ('paid','cancelled') else f'<button onclick="markPaid({inv["id"]})" style="background:#28a745;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;">Mark Paid</button>'}
            </div>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Invoice Nudge</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #212529; }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 40px; }}
    .header h1 {{ font-size: 28px; font-weight: 700; }}
    .header p {{ opacity: 0.85; margin-top: 4px; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 30px 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
    .card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .card .label {{ font-size: 13px; color: #6c757d; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
    .card .value {{ font-size: 30px; font-weight: 700; margin-top: 8px; }}
    .card.outstanding .value {{ color: #667eea; }}
    .card.overdue .value {{ color: #dc3545; }}
    .card.paid .value {{ color: #28a745; }}
    .section {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
    .section-header {{ padding: 20px 24px; border-bottom: 1px solid #e9ecef; display: flex; justify-content: space-between; align-items: center; }}
    .section-header h2 {{ font-size: 18px; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #f8f9fa; padding: 12px 8px; text-align: left; font-size: 13px; font-weight: 600; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }}
    tr:not(:last-child) {{ border-bottom: 1px solid #e9ecef; }}
    tr:hover {{ background: #f8f9fa; }}
    .btn-primary {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; }}
    .btn-run {{ background: #17a2b8; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; }}
    #toast {{ position: fixed; bottom: 30px; right: 30px; background: #333; color: white; padding: 14px 22px; border-radius: 8px; display: none; z-index: 999; font-size: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Invoice Nudge</h1>
    <p>Freelancer invoice tracker with automated payment reminder sequences</p>
  </div>
  <div class="container">
    <div class="cards">
      <div class="card outstanding">
        <div class="label">Total Outstanding</div>
        <div class="value">${'${:,.0f}'.format(total_outstanding)}</div>
      </div>
      <div class="card overdue">
        <div class="label">Overdue Amount</div>
        <div class="value">${'${:,.0f}'.format(overdue_amount)}</div>
      </div>
      <div class="card paid">
        <div class="label">Paid This Month</div>
        <div class="value">${'${:,.0f}'.format(paid_this_month)}</div>
      </div>
    </div>
    <div class="section">
      <div class="section-header">
        <h2>Invoices</h2>
        <button class="btn-run" onclick="runReminders()">Run All Reminders</button>
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Client</th>
              <th>Amount</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    <div style="margin-top:20px;color:#6c757d;font-size:13px;">
      <strong>API Docs:</strong> <a href="/docs" style="color:#667eea;">/docs</a> &nbsp;|&nbsp;
      <strong>Stats:</strong> <a href="/api/stats" style="color:#667eea;">/api/stats</a>
    </div>
  </div>
  <div id="toast"></div>
  <script>
    function toast(msg) {{
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 3500);
    }}
    async function apiPost(url, body) {{
      try {{
        const res = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: body ? JSON.stringify(body) : undefined}});
        const data = await res.json();
        toast(data.message || data.detail || JSON.stringify(data));
        if (res.ok) setTimeout(() => location.reload(), 1500);
      }} catch(e) {{ toast('Error: ' + e.message); }}
    }}
    async function markPaid(id) {{
      try {{
        const res = await fetch('/api/invoices/' + id + '/status', {{method:'PUT', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{status:'paid'}})}});
        const data = await res.json();
        toast(data.message || JSON.stringify(data));
        if (res.ok) setTimeout(() => location.reload(), 1500);
      }} catch(e) {{ toast('Error: ' + e.message); }}
    }}
    async function runReminders() {{
      try {{
        const res = await fetch('/api/run-reminders', {{method:'POST'}});
        const data = await res.json();
        toast('Reminders sent: ' + (data.reminders_sent || 0));
        if (res.ok) setTimeout(() => location.reload(), 2000);
      }} catch(e) {{ toast('Error: ' + e.message); }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/api/clients")
async def create_client(client: ClientCreate):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO clients (name, email, company, created_at) VALUES (?, ?, ?, ?)",
            (client.name, client.email, client.company, datetime.utcnow().isoformat())
        )
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/clients")
async def list_clients():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/invoices")
async def create_invoice(inv: InvoiceCreate):
    with get_db() as conn:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (inv.client_id,)).fetchone()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        existing = conn.execute("SELECT id FROM invoices WHERE invoice_number = ?", (inv.invoice_number,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Invoice number already exists")
        cursor = conn.execute(
            """INSERT INTO invoices (client_id, invoice_number, amount, currency, description, due_date, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)""",
            (inv.client_id, inv.invoice_number, inv.amount, inv.currency,
             inv.description, inv.due_date, datetime.utcnow().isoformat())
        )
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return enrich_invoice(row)


@app.get("/api/invoices")
async def list_invoices():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            ORDER BY i.created_at DESC
        """).fetchall()
    result = [enrich_invoice(r) for r in rows]
    # Auto-update overdue status
    with get_db() as conn:
        today = date.today().isoformat()
        conn.execute(
            "UPDATE invoices SET status='overdue' WHERE status='sent' AND due_date < ?",
            (today,)
        )
    return result


@app.get("/api/invoices/{invoice_id}")
async def get_invoice(invoice_id: int):
    with get_db() as conn:
        row = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")
        reminders = conn.execute(
            "SELECT * FROM reminders WHERE invoice_id = ? ORDER BY sent_at DESC",
            (invoice_id,)
        ).fetchall()
    inv = enrich_invoice(row)
    inv["reminders"] = [dict(r) for r in reminders]
    return inv


@app.put("/api/invoices/{invoice_id}/status")
async def update_invoice_status(invoice_id: int, update: StatusUpdate):
    allowed = {"paid", "cancelled", "draft", "sent", "overdue"}
    if update.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(allowed)}")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")
        paid_at = datetime.utcnow().isoformat() if update.status == "paid" else row["paid_at"]
        conn.execute(
            "UPDATE invoices SET status = ?, paid_at = ? WHERE id = ?",
            (update.status, paid_at, invoice_id)
        )
        updated = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return {"message": f"Invoice status updated to {update.status}", "invoice": enrich_invoice(updated)}


@app.post("/api/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: int):
    with get_db() as conn:
        row = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if row["status"] not in ("draft", "sent"):
            raise HTTPException(status_code=400, detail=f"Cannot send invoice with status '{row['status']}'")

        inv = enrich_invoice(row)
        client = {"name": row["client_name"], "email": row["client_email"], "company": row["company"]}
        subject, body = invoice_sent_template(inv, client)
        sent = send_email(row["client_email"], subject, body)

        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE invoices SET status='sent', sent_at=? WHERE id=?",
            (now, invoice_id)
        )
    return {
        "message": f"Invoice {inv['invoice_number']} sent to {row['client_email']}",
        "email_sent": sent,
        "subject": subject
    }


@app.post("/api/invoices/{invoice_id}/remind")
async def send_reminder(invoice_id: int):
    with get_db() as conn:
        row = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")

        inv = enrich_invoice(row)
        if inv["status"] not in ("sent", "overdue"):
            raise HTTPException(status_code=400, detail="Can only send reminders for sent or overdue invoices")

        days = inv["days_overdue"]
        if days == 0:
            # Force-compute from due_date even if status isn't overdue yet
            try:
                due = date.fromisoformat(inv["due_date"])
                days = max(0, (date.today() - due).days)
            except Exception:
                days = 0

        if days <= 7:
            reminder_type = "polite"
            subject, body = polite_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})
        elif days <= 14:
            reminder_type = "firm"
            subject, body = firm_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})
        else:
            reminder_type = "final"
            subject, body = final_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})

        sent = send_email(row["client_email"], subject, body)
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO reminders (invoice_id, reminder_type, sent_at, email_subject, email_body) VALUES (?,?,?,?,?)",
            (invoice_id, reminder_type, now, subject, body)
        )
        # Auto-escalate status
        if inv["status"] == "sent" and days > 0:
            conn.execute("UPDATE invoices SET status='overdue' WHERE id=?", (invoice_id,))

    return {
        "message": f"{reminder_type.capitalize()} reminder sent for invoice {inv['invoice_number']}",
        "reminder_type": reminder_type,
        "days_overdue": days,
        "email_sent": sent,
        "subject": subject,
        "body": body
    }


@app.post("/api/run-reminders")
async def run_reminders():
    today_str = date.today().isoformat()
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
    reminders_sent = 0
    results = []

    with get_db() as conn:
        # Mark sent invoices as overdue if past due_date
        conn.execute(
            "UPDATE invoices SET status='overdue' WHERE status='sent' AND due_date < ?",
            (today_str,)
        )

        overdue = conn.execute("""
            SELECT i.*, c.name as client_name, c.email as client_email, c.company
            FROM invoices i JOIN clients c ON i.client_id = c.id
            WHERE i.status = 'overdue'
        """).fetchall()

        for row in overdue:
            inv = enrich_invoice(row)
            invoice_id = inv["id"]
            days = inv["days_overdue"]

            recent = conn.execute(
                "SELECT id FROM reminders WHERE invoice_id=? AND sent_at > ? ORDER BY sent_at DESC LIMIT 1",
                (invoice_id, three_days_ago)
            ).fetchone()
            if recent:
                continue

            if days <= 7:
                reminder_type = "polite"
                subject, body = polite_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})
            elif days <= 14:
                reminder_type = "firm"
                subject, body = firm_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})
            else:
                reminder_type = "final"
                subject, body = final_reminder_template(inv, {"name": row["client_name"], "email": row["client_email"]})

            send_email(row["client_email"], subject, body)
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO reminders (invoice_id, reminder_type, sent_at, email_subject, email_body) VALUES (?,?,?,?,?)",
                (invoice_id, reminder_type, now, subject, body)
            )
            reminders_sent += 1
            results.append({
                "invoice_number": inv["invoice_number"],
                "client": row["client_name"],
                "reminder_type": reminder_type,
                "days_overdue": days
            })

    return {
        "message": f"Processed {len(list(overdue))} overdue invoices, sent {reminders_sent} reminders",
        "reminders_sent": reminders_sent,
        "details": results
    }


@app.get("/api/stats")
async def get_stats():
    with get_db() as conn:
        row = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN status NOT IN ('paid','cancelled') THEN amount ELSE 0 END),0) as total_outstanding,
              COALESCE(SUM(CASE WHEN status='overdue' THEN amount ELSE 0 END),0) as overdue_amount,
              COALESCE(SUM(CASE WHEN status='paid' AND strftime('%Y-%m', paid_at) = strftime('%Y-%m','now') THEN amount ELSE 0 END),0) as paid_this_month,
              COUNT(CASE WHEN status NOT IN ('draft','cancelled') THEN 1 END) as invoices_sent,
              COALESCE(AVG(CASE WHEN status='paid' AND sent_at IS NOT NULL AND paid_at IS NOT NULL
                THEN CAST((julianday(paid_at) - julianday(sent_at)) AS INTEGER)
                ELSE NULL END), 0) as avg_days_to_pay
            FROM invoices
        """).fetchone()
    return {
        "total_outstanding": round(row["total_outstanding"], 2),
        "overdue_amount": round(row["overdue_amount"], 2),
        "paid_this_month": round(row["paid_this_month"], 2),
        "invoices_sent": row["invoices_sent"],
        "avg_days_to_pay": round(row["avg_days_to_pay"], 1)
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
