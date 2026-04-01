# Invoice Nudge

**Freelancer invoice tracker with automated payment reminder sequences — stop chasing late payments manually.**

---

## The Problem

- Freelancers spend **4+ hours per week** chasing late payments via manual follow-up emails
- **29% of invoices** are paid late, hurting cash flow for independent workers
- Existing tools (Wave, FreshBooks, QuickBooks) require expensive subscriptions and have no built-in automated reminder sequences
- There is no simple, self-hosted tool that sends escalating reminder emails automatically

Invoice Nudge solves this with a lightweight FastAPI app that tracks invoices, detects when they go overdue, and fires a 3-stage polite → firm → final reminder email sequence — automatically.

---

## Features

- **Client management** — store client name, email, and company
- **Invoice creation and tracking** — create invoices with due dates, amounts, currency, and descriptions
- **3-stage automated reminder emails** — polite (1–7 days late), firm (8–14 days), final notice (15+ days)
- **Overdue detection** — automatically marks invoices as overdue when their due date passes
- **Payment tracking** — mark invoices as paid with timestamp
- **Dashboard** — web UI showing outstanding totals, overdue amount, paid this month, and per-invoice action buttons
- **REST API** — full JSON API for integration with other tools
- **Scheduler script** — designed for cron to run daily at 9 AM and process all overdue invoices

---

## Tech Stack

- **Python 3.10+** with **FastAPI** for the web framework
- **SQLite** for zero-configuration persistence
- **smtplib/ssl** for sending emails (works with Gmail, SendGrid SMTP, Mailgun, etc.)
- **python-dotenv** for environment configuration
- **uvicorn** for the ASGI server

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Everaldtah/invoice-nudge.git
cd invoice-nudge
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your SMTP credentials and company info:

```env
DATABASE_URL=./invoicenudge.db
PORT=8000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=invoices@yourcompany.com
FROM_NAME=Your Name
COMPANY_NAME=Your Company LLC
COMPANY_ADDRESS=123 Main St, City, State 12345
BASE_URL=http://localhost:8000
```

> **Gmail users:** Use an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password). Enable 2FA first, then generate an app password.

### 4. Run the application

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) to see the dashboard.

---

## Usage Guide

### Dashboard

Visit `http://localhost:8000` to see:
- Summary cards: Total Outstanding, Overdue Amount, Paid This Month
- Invoice table with color-coded status badges:
  - **Green** = Paid
  - **Red** = Overdue
  - **Yellow** = Sent (awaiting payment)
  - **Grey** = Draft
- Per-invoice action buttons: **Send**, **Remind**, **Mark Paid**
- **Run All Reminders** button to process all overdue invoices at once

### API Documentation

Interactive docs available at `http://localhost:8000/docs` (Swagger UI).

---

## API Reference

### Clients

**Create a client**
```bash
curl -X POST http://localhost:8000/api/clients \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@acme.com", "company": "Acme Corp"}'
```

**List all clients**
```bash
curl http://localhost:8000/api/clients
```

### Invoices

**Create an invoice**
```bash
curl -X POST http://localhost:8000/api/invoices \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "invoice_number": "INV-006",
    "amount": 1500.00,
    "currency": "USD",
    "description": "Website development - Sprint 3",
    "due_date": "2026-04-30"
  }'
```

**List all invoices**
```bash
curl http://localhost:8000/api/invoices
```

**Get invoice details**
```bash
curl http://localhost:8000/api/invoices/1
```

**Send an invoice to client (email + status update)**
```bash
curl -X POST http://localhost:8000/api/invoices/1/send
```

**Send a reminder email**
```bash
curl -X POST http://localhost:8000/api/invoices/1/remind
```

**Mark invoice as paid**
```bash
curl -X PUT http://localhost:8000/api/invoices/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "paid"}'
```

**Cancel an invoice**
```bash
curl -X PUT http://localhost:8000/api/invoices/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "cancelled"}'
```

### Reminders & Stats

**Run reminders for all overdue invoices**
```bash
curl -X POST http://localhost:8000/api/run-reminders
```

**Get financial stats**
```bash
curl http://localhost:8000/api/stats
```

Sample response:
```json
{
  "total_outstanding": 5750.00,
  "overdue_amount": 2750.00,
  "paid_this_month": 2500.00,
  "invoices_sent": 4,
  "avg_days_to_pay": 15.3
}
```

---

## Email Reminder Sequence

Invoice Nudge automatically selects the right tone based on how overdue the invoice is:

| Days Overdue | Reminder Type | Tone |
|---|---|---|
| 1 – 7 days | **Polite** | Friendly reminder, assumes oversight |
| 8 – 14 days | **Firm** | Clear urgency, requests immediate action |
| 15+ days | **Final Notice** | Strong language, mentions escalation options |

**Throttling:** Only one reminder is sent per invoice per 3-day period, preventing spam.

**Auto-escalation:** Each time `/api/run-reminders` is called, Invoice Nudge automatically selects the appropriate template based on the current days-overdue count. As time passes, reminders automatically escalate from polite → firm → final.

### Setting Up Automatic Daily Reminders (cron)

```bash
# Run reminders every day at 9 AM
0 9 * * * /path/to/venv/bin/python /path/to/invoice-nudge/scheduler.py >> /var/log/invoice-nudge.log 2>&1
```

---

## Monetization

**Free tier:** Up to 3 active clients, unlimited invoices, all 3 reminder stages, full API access.

**Pro — $12/month:**
- Unlimited clients
- Custom email templates (brand your reminders)
- Stripe payment links embedded in invoice emails
- PDF invoice generation
- Priority support

**Why this has traction:**
- **59 million freelancers** in the US alone (Upwork/Freelancers Union data)
- Late payment is the **#1 complaint** among independent contractors and consultants
- Wave Invoicing is free but has **zero automation** — users still manually send follow-ups
- FreshBooks charges $19+/month just for basic invoicing; no escalating reminders
- Invoice Nudge is the only **self-hosted, open-source** tool purpose-built for automated reminder sequences

---

## License

MIT License — free to use, modify, and deploy.
