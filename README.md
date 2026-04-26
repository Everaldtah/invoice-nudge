# Invoice Nudge

**Smart overdue invoice follow-up automation — AI-crafted escalating payment reminders so freelancers get paid without awkward emails.**

## Problem It Solves

Freelancers and small agencies lose an average of 13% of revenue to late payments, and 54% say chasing payments is their most stressful business task. The hardest part isn't tracking — it's writing the follow-up email: too aggressive ruins the relationship, too soft gets ignored. Invoice Nudge automates a 5-stage escalating sequence (friendly → polite → firm → final notice → collections warning), with each email AI-generated to match the relationship context.

## Features

- **Invoice tracking** — full ledger with issue date, due date, amount, payment links
- **5-stage nudge sequence** — automatically escalates tone over 30 days
  1. Day 1 overdue: Friendly reminder
  2. Day 7: Polite follow-up
  3. Day 14: Firm notice
  4. Day 21: Final notice
  5. Day 30: Collections warning
- **AI email generation** — Claude writes each email using actual client name, invoice details, and business context
- **Smart scheduling** — auto-nudge engine determines which invoices need follow-up today
- **Multi-client support** — manage invoices across all clients from one account
- **Payment stats** — collection rate, average days to pay, overdue totals
- **Mark-paid workflow** — instantly stop follow-ups when payment arrives

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **AI**: Anthropic Claude (claude-haiku-4-5-20251001)
- **Database**: SQLite
- **Email**: SMTP (Gmail, Mailgun, etc.)

## Installation

```bash
git clone https://github.com/Everaldtah/invoice-nudge
cd invoice-nudge
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with SMTP credentials and ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8000
```

## Usage Guide

### 1. Register yourself as a freelancer
```bash
curl -X POST http://localhost:8000/freelancers \
  -H "Content-Type: application/json" \
  -d '{"id":"me","name":"Your Name","email":"you@email.com","business_name":"Your Studio"}'
```

### 2. Add a client
```bash
curl -X POST http://localhost:8000/freelancers/me/clients \
  -H "Content-Type: application/json" \
  -d '{"id":"client_abc","name":"Bob Johnson","email":"bob@company.com","company":"Acme Inc"}'
```

### 3. Create an invoice
```bash
curl -X POST http://localhost:8000/freelancers/me/invoices \
  -H "Content-Type: application/json" \
  -d '{
    "id":"inv_001","client_id":"client_abc",
    "invoice_number":"INV-2025-001","amount":2500,
    "issue_date":"2025-01-01","due_date":"2025-01-31",
    "description":"Brand identity project",
    "payment_link":"https://stripe.com/your-link"
  }'
```

### 4. Send a nudge (or let auto-run handle it)
```bash
# Manual nudge
curl -X POST http://localhost:8000/invoices/inv_001/nudge

# Auto-nudge all overdue invoices
curl -X POST http://localhost:8000/freelancers/me/run-nudges
```

### 5. Mark paid when money arrives
```bash
curl -X PUT http://localhost:8000/invoices/inv_001/mark-paid
```

### 6. View your stats
```bash
curl http://localhost:8000/freelancers/me/stats
```

## Automation Setup

Run `POST /freelancers/{id}/run-nudges` daily via cron to fully automate the sequence:

```bash
# crontab -e
0 9 * * * curl -X POST http://localhost:8000/freelancers/me/run-nudges
```

## Monetization Model

| Plan | Price | Invoices/mo |
|------|-------|------------|
| Free | $0/mo | 3 active invoices |
| Freelancer | $15/mo | Unlimited invoices, AI emails |
| Agency | $49/mo | 5 users, custom templates, Stripe integration |
| White-label | $149/mo | Rebrandable, resell to clients |

**Target users**: freelancers, consultants, design/dev agencies, contractors — anyone doing B2B invoicing.
