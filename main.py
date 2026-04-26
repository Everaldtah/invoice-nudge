from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, date, timedelta
import sqlite3
import os
import smtplib
import httpx
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI(title="Invoice Nudge", description="Smart overdue invoice follow-up automation for freelancers and SMBs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("DB_PATH", "invoices.db")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS freelancers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            business_name TEXT,
            payment_terms TEXT DEFAULT 'Net 30',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            freelancer_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            payment_reliability TEXT DEFAULT 'unknown',
            FOREIGN KEY (freelancer_id) REFERENCES freelancers(id)
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            freelancer_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            invoice_number TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            issue_date DATE NOT NULL,
            due_date DATE NOT NULL,
            description TEXT,
            payment_link TEXT,
            status TEXT DEFAULT 'unpaid',
            paid_at DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (freelancer_id) REFERENCES freelancers(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS nudges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            nudge_number INTEGER NOT NULL,
            days_overdue INTEGER,
            tone TEXT,
            subject TEXT,
            body TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );
    """)
    conn.commit()
    conn.close()


init_db()


class FreelancerCreate(BaseModel):
    id: str
    name: str
    email: str
    business_name: Optional[str] = None
    payment_terms: Optional[str] = "Net 30"


class ClientCreate(BaseModel):
    id: str
    name: str
    email: str
    company: Optional[str] = None


class InvoiceCreate(BaseModel):
    id: str
    client_id: str
    invoice_number: str
    amount: float
    currency: Optional[str] = "USD"
    issue_date: str
    due_date: str
    description: Optional[str] = None
    payment_link: Optional[str] = None


NUDGE_TONES = {
    1: {"name": "friendly_reminder", "days_after": 1, "label": "Friendly Reminder"},
    2: {"name": "polite_follow_up", "days_after": 7, "label": "Polite Follow-up"},
    3: {"name": "firm", "days_after": 14, "label": "Firm Notice"},
    4: {"name": "final_notice", "days_after": 21, "label": "Final Notice"},
    5: {"name": "collections", "days_after": 30, "label": "Collections Warning"},
}


async def generate_nudge_email(invoice: dict, client: dict, freelancer: dict, nudge_num: int, days_overdue: int) -> dict:
    tone_info = NUDGE_TONES.get(nudge_num, NUDGE_TONES[5])

    if not ANTHROPIC_API_KEY:
        subject = f"[{tone_info['label']}] Invoice {invoice['invoice_number']} - ${invoice['amount']:,.2f} Overdue"
        body = f"""Hi {client['name']},

I hope you're doing well. I wanted to follow up on Invoice #{invoice['invoice_number']} for ${invoice['amount']:,.2f} {invoice['currency']}, which was due on {invoice['due_date']}.

This is follow-up #{nudge_num} ({days_overdue} days overdue).

{f"You can pay online here: {invoice['payment_link']}" if invoice.get('payment_link') else "Please process this payment at your earliest convenience."}

Please let me know if you have any questions or if there's an issue with the invoice.

Best regards,
{freelancer['name']}
{freelancer.get('business_name', '')}"""
        return {"subject": subject, "body": body}

    tone_prompts = {
        "friendly_reminder": "gentle and friendly, assuming this is just an oversight",
        "polite_follow_up": "polite but slightly more direct, noting this is a follow-up",
        "firm": "professional and firm, making clear payment is required promptly",
        "final_notice": "serious and direct, indicating this is the last notice before escalation",
        "collections": "formal and stern, mentioning potential referral to collections agency",
    }

    tone_desc = tone_prompts[tone_info["name"]]
    payment_link_text = f"Payment can be made here: {invoice['payment_link']}" if invoice.get("payment_link") else ""

    prompt = f"""Write a payment follow-up email for an overdue invoice.

Context:
- Freelancer/Sender: {freelancer['name']} ({freelancer.get('business_name', 'Freelancer')})
- Client: {client['name']} at {client.get('company', 'their company')}
- Invoice #: {invoice['invoice_number']}
- Amount: ${invoice['amount']:,.2f} {invoice['currency']}
- Due date: {invoice['due_date']}
- Days overdue: {days_overdue}
- This is follow-up #{nudge_num} of 5
- Tone required: {tone_desc}
- Invoice description: {invoice.get('description', 'Professional services')}
{payment_link_text}

Write the email with:
1. Subject line (prefix with "Subject: ")
2. Blank line
3. Email body

Keep it concise (under 150 words). Sound human. Do not use placeholders like [NAME] — use the actual names provided."""

    async with httpx.AsyncClient() as client_http:
        resp = await client_http.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 512, "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        text = resp.json()["content"][0]["text"]

    lines = text.strip().split("\n")
    subject_line = ""
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("Subject:"):
            subject_line = line.replace("Subject:", "").strip()
        else:
            body_lines.extend(lines[i:])
            break

    return {"subject": subject_line or f"Invoice {invoice['invoice_number']} — Payment Overdue", "body": "\n".join(body_lines).strip()}


def send_email(to_email: str, subject: str, body: str, from_name: str):
    if not SMTP_USER:
        print(f"\n[EMAIL SKIPPED — SMTP not configured]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        return False
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
    return True


@app.post("/freelancers", status_code=201)
def create_freelancer(f: FreelancerCreate):
    conn = get_db()
    try:
        conn.execute("INSERT INTO freelancers (id, name, email, business_name, payment_terms) VALUES (?,?,?,?,?)",
                     (f.id, f.name, f.email, f.business_name, f.payment_terms))
        conn.commit()
        return {"id": f.id, "name": f.name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Freelancer ID exists")
    finally:
        conn.close()


@app.post("/freelancers/{freelancer_id}/clients", status_code=201)
def add_client(freelancer_id: str, c: ClientCreate):
    conn = get_db()
    fl = conn.execute("SELECT id FROM freelancers WHERE id = ?", (freelancer_id,)).fetchone()
    if not fl:
        conn.close()
        raise HTTPException(status_code=404, detail="Freelancer not found")
    try:
        conn.execute("INSERT INTO clients (id, freelancer_id, name, email, company) VALUES (?,?,?,?,?)",
                     (c.id, freelancer_id, c.name, c.email, c.company))
        conn.commit()
        return {"id": c.id, "name": c.name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Client ID exists")
    finally:
        conn.close()


@app.post("/freelancers/{freelancer_id}/invoices", status_code=201)
def create_invoice(freelancer_id: str, inv: InvoiceCreate):
    conn = get_db()
    fl = conn.execute("SELECT id FROM freelancers WHERE id = ?", (freelancer_id,)).fetchone()
    if not fl:
        conn.close()
        raise HTTPException(status_code=404, detail="Freelancer not found")
    cl = conn.execute("SELECT id FROM clients WHERE id = ? AND freelancer_id = ?", (inv.client_id, freelancer_id)).fetchone()
    if not cl:
        conn.close()
        raise HTTPException(status_code=404, detail="Client not found")
    try:
        conn.execute("""INSERT INTO invoices (id, freelancer_id, client_id, invoice_number, amount, currency,
                        issue_date, due_date, description, payment_link)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (inv.id, freelancer_id, inv.client_id, inv.invoice_number, inv.amount, inv.currency,
                      inv.issue_date, inv.due_date, inv.description, inv.payment_link))
        conn.commit()
        return {"id": inv.id, "invoice_number": inv.invoice_number}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Invoice ID exists")
    finally:
        conn.close()


@app.get("/freelancers/{freelancer_id}/invoices")
def list_invoices(freelancer_id: str, status: Optional[str] = None):
    conn = get_db()
    today = date.today().isoformat()
    query = """SELECT i.*, c.name as client_name, c.email as client_email, c.company as client_company
               FROM invoices i JOIN clients c ON i.client_id = c.id
               WHERE i.freelancer_id = ?"""
    params = [freelancer_id]
    if status:
        query += " AND i.status = ?"
        params.append(status)
    query += " ORDER BY i.due_date ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if d["status"] == "unpaid":
            due = date.fromisoformat(d["due_date"])
            d["days_overdue"] = (date.today() - due).days
            d["is_overdue"] = d["days_overdue"] > 0
        result.append(d)
    return result


@app.put("/invoices/{invoice_id}/mark-paid")
def mark_paid(invoice_id: str):
    conn = get_db()
    inv = conn.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    conn.execute("UPDATE invoices SET status='paid', paid_at=? WHERE id=?", (date.today().isoformat(), invoice_id))
    conn.commit()
    conn.close()
    return {"message": "Marked as paid"}


@app.post("/invoices/{invoice_id}/nudge")
async def send_nudge(invoice_id: str, background_tasks: BackgroundTasks):
    conn = get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv["status"] == "paid":
        conn.close()
        raise HTTPException(status_code=400, detail="Invoice already paid")

    client = conn.execute("SELECT * FROM clients WHERE id = ?", (inv["client_id"],)).fetchone()
    freelancer = conn.execute("SELECT * FROM freelancers WHERE id = ?", (inv["freelancer_id"],)).fetchone()

    nudge_count = conn.execute("SELECT COUNT(*) as cnt FROM nudges WHERE invoice_id = ?", (invoice_id,)).fetchone()["cnt"]
    nudge_num = min(nudge_count + 1, 5)

    due = date.fromisoformat(inv["due_date"])
    days_overdue = (date.today() - due).days

    email_content = await generate_nudge_email(dict(inv), dict(client), dict(freelancer), nudge_num, days_overdue)

    conn.execute("INSERT INTO nudges (invoice_id, nudge_number, days_overdue, tone, subject, body) VALUES (?,?,?,?,?,?)",
                 (invoice_id, nudge_num, days_overdue, NUDGE_TONES[nudge_num]["name"], email_content["subject"], email_content["body"]))
    conn.commit()
    conn.close()

    background_tasks.add_task(send_email, client["email"], email_content["subject"], email_content["body"], freelancer["name"])

    return {
        "nudge_number": nudge_num,
        "tone": NUDGE_TONES[nudge_num]["name"],
        "days_overdue": days_overdue,
        "subject": email_content["subject"],
        "body": email_content["body"],
        "sent_to": client["email"],
    }


@app.post("/freelancers/{freelancer_id}/run-nudges")
async def run_auto_nudges(freelancer_id: str, background_tasks: BackgroundTasks):
    """Auto-send nudges for all overdue invoices that are due for a follow-up."""
    conn = get_db()
    today = date.today()

    overdue = conn.execute("""
        SELECT i.id, i.due_date
        FROM invoices i
        WHERE i.freelancer_id = ? AND i.status = 'unpaid' AND i.due_date < ?
    """, (freelancer_id, today.isoformat())).fetchall()

    sent = []
    skipped = []

    for inv_row in overdue:
        invoice_id = inv_row["id"]
        due = date.fromisoformat(inv_row["due_date"])
        days_overdue = (today - due).days

        last_nudge = conn.execute(
            "SELECT nudge_number, sent_at FROM nudges WHERE invoice_id = ? ORDER BY nudge_number DESC LIMIT 1",
            (invoice_id,)
        ).fetchone()

        nudge_num = (last_nudge["nudge_number"] if last_nudge else 0) + 1
        if nudge_num > 5:
            skipped.append({"invoice_id": invoice_id, "reason": "max nudges reached"})
            continue

        expected_day = NUDGE_TONES[nudge_num]["days_after"]
        if days_overdue < expected_day:
            skipped.append({"invoice_id": invoice_id, "reason": f"not yet due for nudge #{nudge_num} (need {expected_day} days overdue, have {days_overdue})"})
            continue

        if last_nudge:
            last_sent = datetime.fromisoformat(last_nudge["sent_at"]).date()
            if (today - last_sent).days < 1:
                skipped.append({"invoice_id": invoice_id, "reason": "nudge sent today already"})
                continue

        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (inv["client_id"],)).fetchone()
        freelancer = conn.execute("SELECT * FROM freelancers WHERE id = ?", (inv["freelancer_id"],)).fetchone()

        email_content = await generate_nudge_email(dict(inv), dict(client), dict(freelancer), nudge_num, days_overdue)

        conn.execute("INSERT INTO nudges (invoice_id, nudge_number, days_overdue, tone, subject, body) VALUES (?,?,?,?,?,?)",
                     (invoice_id, nudge_num, days_overdue, NUDGE_TONES[nudge_num]["name"], email_content["subject"], email_content["body"]))

        background_tasks.add_task(send_email, client["email"], email_content["subject"], email_content["body"], freelancer["name"])
        sent.append({"invoice_id": invoice_id, "nudge_num": nudge_num, "days_overdue": days_overdue})

    conn.commit()
    conn.close()
    return {"sent": len(sent), "skipped": len(skipped), "details": sent}


@app.get("/freelancers/{freelancer_id}/stats")
def freelancer_stats(freelancer_id: str):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt, SUM(amount) as total FROM invoices WHERE freelancer_id = ?", (freelancer_id,)).fetchone()
    paid = conn.execute("SELECT COUNT(*) as cnt, SUM(amount) as total FROM invoices WHERE freelancer_id = ? AND status='paid'", (freelancer_id,)).fetchone()
    overdue = conn.execute("SELECT COUNT(*) as cnt, SUM(amount) as total FROM invoices WHERE freelancer_id = ? AND status='unpaid' AND due_date < date('now')", (freelancer_id,)).fetchone()
    avg_days = conn.execute("""
        SELECT AVG(julianday(paid_at) - julianday(due_date)) as avg_days
        FROM invoices WHERE freelancer_id = ? AND status = 'paid' AND paid_at IS NOT NULL
    """, (freelancer_id,)).fetchone()
    conn.close()
    return {
        "total_invoices": total["cnt"],
        "total_billed": round(total["total"] or 0, 2),
        "paid_count": paid["cnt"],
        "paid_amount": round(paid["total"] or 0, 2),
        "overdue_count": overdue["cnt"],
        "overdue_amount": round(overdue["total"] or 0, 2),
        "collection_rate": round((paid["cnt"] / total["cnt"] * 100) if total["cnt"] else 0, 1),
        "avg_days_to_pay": round(avg_days["avg_days"] or 0, 1),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "invoice-nudge"}
