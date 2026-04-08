# Invoice Nudge

> Smart invoice follow-up automation for freelancers and agencies — never chase a payment manually again.

## The Problem

Freelancers and small agencies lose thousands of dollars every year to late payments — not because clients refuse to pay, but because invoices get buried in inboxes. Sending follow-up emails is awkward, time-consuming, and often forgotten. Most accounting tools (QuickBooks, FreshBooks) don't have smart, customizable follow-up sequences.

## What It Does

Invoice Nudge automatically sends the right follow-up email at the right time — before the due date, 1 day after, 1 week after, and a final notice — all personalized to your client. Tracks payment history to learn which clients pay late and adjusts timing accordingly.

## Features

- **Automated nudge sequences** — configurable email cadence per invoice/client
- **Smart timing** — sends reminders based on days relative to due date
- **Template engine** — personalized emails with client name, invoice number, amount, payment link
- **Payment tracking** — mark invoices as paid, track avg days-to-pay per client
- **Dashboard** — see all outstanding invoices, overdue amounts, nudge history
- **SMTP support** — use your own email so nudges come from your address
- **REST API** — integrate with any frontend or accounting tool

## Tech Stack

- **Backend**: Node.js / Express
- **Database**: SQLite (better-sqlite3) — zero-config, file-based
- **Email**: Nodemailer (works with Gmail, Outlook, any SMTP)
- **Scheduler**: node-cron — runs hourly checks

## Installation

```bash
git clone https://github.com/Everaldtah/invoice-nudge
cd invoice-nudge
npm install
cp .env.example .env
# edit .env with your SMTP settings (optional for dry-run mode)
node src/seed.js   # create demo data
npm start
```

Server starts at http://localhost:3000

## Usage

### Create a user account
```bash
curl -X POST http://localhost:3000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Jane Smith", "email": "jane@smith.com", "company": "Jane Design"}'
```

### Add a client
```bash
curl -X POST http://localhost:3000/api/clients \
  -H "Content-Type: application/json" \
  -d '{"userId": "USER_ID", "name": "Acme Corp", "email": "billing@acme.com"}'
```

### Create an invoice
```bash
curl -X POST http://localhost:3000/api/invoices \
  -H "Content-Type: application/json" \
  -d '{"userId": "USER_ID", "clientId": "CLIENT_ID", "invoiceNumber": "INV-001",
       "amount": 3500, "dueDate": "2026-04-20", "paymentLink": "https://stripe.com/pay/..."}'
```

### View dashboard
```bash
curl http://localhost:3000/api/dashboard/USER_ID
```

## Nudge Sequence (Default)

| Step | When | Message |
|------|------|---------|
| 1 | 3 days before due | Friendly reminder |
| 2 | 1 day after due | Gentle follow-up |
| 3 | 7 days overdue | More direct nudge |
| 4 | 21 days overdue | Final notice |

## Monetization Model

| Plan | Price | Features |
|------|-------|---------|
| Free | $0 | Up to 3 clients, basic sequences |
| Solo | $12/mo | Unlimited clients, custom sequences, payment link tracking |
| Agency | $39/mo | Multi-seat, white-label emails, Stripe integration, analytics |

**Target customers**: Freelancers, web agencies, consultants, photographers, designers.
**Market size**: 59M+ freelancers in the US alone. Even 0.1% at $12/mo = $710K ARR.
