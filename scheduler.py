#!/usr/bin/env python3
"""
Invoice Nudge Scheduler
-----------------------
Calls the /api/run-reminders endpoint to process all overdue invoices
and send appropriate reminder emails.

Designed to run via cron:
  0 9 * * * /usr/bin/python3 /path/to/scheduler.py >> /var/log/invoice-nudge.log 2>&1

Or with a virtual environment:
  0 9 * * * /path/to/venv/bin/python /path/to/scheduler.py >> /var/log/invoice-nudge.log 2>&1
"""

import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LOG_PREFIX = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [invoice-nudge-scheduler]"


def log(msg: str):
    print(f"{LOG_PREFIX} {msg}", flush=True)


def run_reminders():
    url = f"{BASE_URL}/api/run-reminders"
    log(f"Calling {url} ...")
    try:
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        reminders_sent = data.get("reminders_sent", 0)
        message = data.get("message", "")
        log(f"SUCCESS: {message}")
        if reminders_sent > 0:
            details = data.get("details", [])
            for item in details:
                log(
                    f"  - Reminded: Invoice {item['invoice_number']} | "
                    f"Client: {item['client']} | "
                    f"Type: {item['reminder_type'].upper()} | "
                    f"Days overdue: {item['days_overdue']}"
                )
        else:
            log("No reminders were needed at this time.")
        return reminders_sent
    except requests.exceptions.ConnectionError:
        log(f"ERROR: Could not connect to {url}. Is the server running?")
        sys.exit(1)
    except requests.exceptions.Timeout:
        log(f"ERROR: Request to {url} timed out.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        log(f"ERROR: HTTP {response.status_code} — {e}")
        sys.exit(1)
    except Exception as e:
        log(f"ERROR: Unexpected error — {e}")
        sys.exit(1)


def get_stats():
    url = f"{BASE_URL}/api/stats"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        stats = response.json()
        log(
            f"Stats — Outstanding: ${stats['total_outstanding']:,.2f} | "
            f"Overdue: ${stats['overdue_amount']:,.2f} | "
            f"Paid this month: ${stats['paid_this_month']:,.2f} | "
            f"Avg days to pay: {stats['avg_days_to_pay']}"
        )
    except Exception as e:
        log(f"Could not fetch stats: {e}")


if __name__ == "__main__":
    log("=== Invoice Nudge Scheduler Starting ===")
    count = run_reminders()
    get_stats()
    log(f"=== Done. Total reminders sent: {count} ===")
