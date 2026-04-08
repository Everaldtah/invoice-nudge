'use strict';

const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = process.env.DATABASE_PATH || path.join(__dirname, '..', 'invoice_nudge.db');
const db = new Database(DB_PATH);

// Enable WAL mode for better concurrency
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    company TEXT,
    smtp_host TEXT,
    smtp_port INTEGER DEFAULT 587,
    smtp_user TEXT,
    smtp_pass TEXT,
    from_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    company TEXT,
    notes TEXT,
    avg_days_to_pay REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    issued_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending | overdue | paid | cancelled
    description TEXT,
    payment_link TEXT,
    pdf_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    paid_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (client_id) REFERENCES clients(id)
  );

  CREATE TABLE IF NOT EXISTS nudge_sequences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS nudge_steps (
    id TEXT PRIMARY KEY,
    sequence_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    days_after_due INTEGER NOT NULL,  -- negative = before due, positive = after
    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,
    FOREIGN KEY (sequence_id) REFERENCES nudge_sequences(id)
  );

  CREATE TABLE IF NOT EXISTS nudge_logs (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    sent_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'sent',  -- sent | failed | skipped
    error TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (step_id) REFERENCES nudge_steps(id)
  );
`);

module.exports = db;
