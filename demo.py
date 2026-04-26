"""Demo script — creates a freelancer, clients, and overdue invoices, then triggers nudges."""
import httpx
from datetime import date, timedelta

BASE = "http://localhost:8000"


def run_demo():
    c = httpx.Client(base_url=BASE)

    print("Creating freelancer...")
    c.post("/freelancers", json={
        "id": "fl_001",
        "name": "Alex Rivera",
        "email": "alex@freelance.dev",
        "business_name": "Rivera Creative",
        "payment_terms": "Net 15",
    })

    print("Adding clients...")
    c.post("/freelancers/fl_001/clients", json={"id": "cl_001", "name": "Jordan Chen", "email": "jordan@startup.co", "company": "TechStart Inc"})
    c.post("/freelancers/fl_001/clients", json={"id": "cl_002", "name": "Maria Santos", "email": "maria@agency.com", "company": "Creative Agency"})

    overdue_30 = (date.today() - timedelta(days=30)).isoformat()
    overdue_7 = (date.today() - timedelta(days=7)).isoformat()
    due_today = date.today().isoformat()

    print("Creating invoices...")
    c.post("/freelancers/fl_001/invoices", json={
        "id": "inv_001", "client_id": "cl_001",
        "invoice_number": "INV-2024-001", "amount": 3500.00,
        "issue_date": (date.today() - timedelta(days=45)).isoformat(),
        "due_date": overdue_30, "description": "Website redesign — Phase 1",
        "payment_link": "https://stripe.com/pay/example",
    })
    c.post("/freelancers/fl_001/invoices", json={
        "id": "inv_002", "client_id": "cl_002",
        "invoice_number": "INV-2024-002", "amount": 850.00,
        "issue_date": (date.today() - timedelta(days=22)).isoformat(),
        "due_date": overdue_7, "description": "Logo design and brand kit",
    })

    print("\nInvoice stats:")
    stats = c.get("/freelancers/fl_001/stats").json()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\nRunning auto-nudges...")
    result = c.post("/freelancers/fl_001/run-nudges").json()
    print(f"  Sent: {result['sent']}, Skipped: {result['skipped']}")
    for d in result.get("details", []):
        print(f"  - {d['invoice_id']}: nudge #{d['nudge_num']} ({d['days_overdue']} days overdue)")

    print("\nManual nudge for INV-001...")
    nudge = c.post("/invoices/inv_001/nudge").json()
    print(f"  Subject: {nudge['subject']}")
    print(f"  Tone: {nudge['tone']}")
    print(f"\n--- EMAIL BODY ---")
    print(nudge['body'])


if __name__ == "__main__":
    run_demo()
