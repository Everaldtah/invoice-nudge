'use strict';

const express = require('express');
const { v4: uuidv4 } = require('uuid');
const dayjs = require('dayjs');
const db = require('../database');

const router = express.Router();

// List invoices for a user
router.get('/', (req, res) => {
  const { userId, status, clientId } = req.query;
  if (!userId) return res.status(400).json({ error: 'userId required' });

  let query = `
    SELECT i.*, c.name as client_name, c.email as client_email
    FROM invoices i
    JOIN clients c ON i.client_id = c.id
    WHERE i.user_id = ?
  `;
  const params = [userId];
  if (status) { query += ' AND i.status = ?'; params.push(status); }
  if (clientId) { query += ' AND i.client_id = ?'; params.push(clientId); }
  query += ' ORDER BY i.due_date ASC';

  const invoices = db.prepare(query).all(...params);
  res.json(invoices);
});

// Create invoice
router.post('/', (req, res) => {
  const { userId, clientId, invoiceNumber, amount, currency = 'USD',
          issuedDate, dueDate, description, paymentLink } = req.body;

  if (!userId || !clientId || !invoiceNumber || !amount || !dueDate) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  const client = db.prepare('SELECT * FROM clients WHERE id = ? AND user_id = ?').get(clientId, userId);
  if (!client) return res.status(404).json({ error: 'Client not found' });

  const id = uuidv4();
  const issued = issuedDate || dayjs().format('YYYY-MM-DD');

  db.prepare(`
    INSERT INTO invoices (id, user_id, client_id, invoice_number, amount, currency,
                          issued_date, due_date, description, payment_link)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(id, userId, clientId, invoiceNumber, amount, currency, issued, dueDate, description, paymentLink);

  // Assign default nudge sequence
  const seq = db.prepare('SELECT id FROM nudge_sequences WHERE user_id = ? AND is_default = 1').get(userId);
  if (!seq) {
    _createDefaultSequence(userId);
  }

  res.status(201).json(db.prepare('SELECT * FROM invoices WHERE id = ?').get(id));
});

// Mark as paid
router.put('/:id/mark-paid', (req, res) => {
  const { id } = req.params;
  const { userId } = req.body;

  const invoice = db.prepare('SELECT * FROM invoices WHERE id = ? AND user_id = ?').get(id, userId);
  if (!invoice) return res.status(404).json({ error: 'Invoice not found' });

  const paidAt = dayjs().toISOString();
  db.prepare("UPDATE invoices SET status = 'paid', paid_at = ? WHERE id = ?").run(paidAt, id);

  // Update client's avg days to pay
  const daysToPay = dayjs(paidAt).diff(dayjs(invoice.due_date), 'day');
  db.prepare(`
    UPDATE clients
    SET avg_days_to_pay = (avg_days_to_pay * 0.7 + ? * 0.3)
    WHERE id = ?
  `).run(daysToPay, invoice.client_id);

  res.json({ success: true, paidAt });
});

// Get overdue invoices
router.get('/overdue', (req, res) => {
  const { userId } = req.query;
  if (!userId) return res.status(400).json({ error: 'userId required' });

  const today = dayjs().format('YYYY-MM-DD');
  const overdue = db.prepare(`
    SELECT i.*, c.name as client_name, c.email as client_email,
           julianday('now') - julianday(i.due_date) as days_overdue
    FROM invoices i
    JOIN clients c ON i.client_id = c.id
    WHERE i.user_id = ? AND i.status IN ('pending', 'overdue')
    AND i.due_date < ?
    ORDER BY days_overdue DESC
  `).all(userId, today);

  // Mark them as overdue in DB
  if (overdue.length > 0) {
    const ids = overdue.map(i => `'${i.id}'`).join(',');
    db.prepare(`UPDATE invoices SET status = 'overdue' WHERE id IN (${ids})`).run();
  }

  res.json(overdue);
});

// Get nudge history for an invoice
router.get('/:id/nudges', (req, res) => {
  const logs = db.prepare(`
    SELECT nl.*, ns.subject_template, ns.days_after_due, ns.step_number
    FROM nudge_logs nl
    JOIN nudge_steps ns ON nl.step_id = ns.id
    WHERE nl.invoice_id = ?
    ORDER BY nl.sent_at DESC
  `).all(req.params.id);
  res.json(logs);
});

function _createDefaultSequence(userId) {
  const seqId = uuidv4();
  db.prepare(`
    INSERT INTO nudge_sequences (id, user_id, name, is_default) VALUES (?, ?, ?, 1)
  `).run(seqId, userId, 'Default Follow-up');

  const steps = [
    {
      days: -3,
      subject: 'Invoice {{invoice_number}} due in 3 days — {{client_name}}',
      body: `Hi {{client_name}},\n\nJust a friendly reminder that invoice {{invoice_number}} for {{currency}} {{amount}} is due on {{due_date}}.\n\n{{payment_link_text}}\n\nThank you!\n{{sender_name}}`
    },
    {
      days: 1,
      subject: 'Invoice {{invoice_number}} was due yesterday',
      body: `Hi {{client_name}},\n\nI wanted to follow up — invoice {{invoice_number}} for {{currency}} {{amount}} was due {{due_date}}.\n\nIf you've already sent payment, please ignore this. Otherwise, a quick update would be appreciated.\n\n{{payment_link_text}}\n\nBest,\n{{sender_name}}`
    },
    {
      days: 7,
      subject: 'Overdue: Invoice {{invoice_number}} — {{days_overdue}} days past due',
      body: `Hi {{client_name}},\n\nInvoice {{invoice_number}} for {{currency}} {{amount}} is now {{days_overdue}} days past due.\n\nPlease arrange payment at your earliest convenience to avoid any service interruption.\n\n{{payment_link_text}}\n\n{{sender_name}}`
    },
    {
      days: 21,
      subject: 'Final Notice: Invoice {{invoice_number}}',
      body: `Hi {{client_name}},\n\nThis is a final notice for invoice {{invoice_number}} totaling {{currency}} {{amount}}, which is {{days_overdue}} days overdue.\n\nPlease contact me immediately to resolve this. If I don't hear back within 5 business days, I may need to pursue other options.\n\n{{payment_link_text}}\n\n{{sender_name}}`
    }
  ];

  for (let i = 0; i < steps.length; i++) {
    db.prepare(`
      INSERT INTO nudge_steps (id, sequence_id, step_number, days_after_due, subject_template, body_template)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(uuidv4(), seqId, i + 1, steps[i].days, steps[i].subject, steps[i].body);
  }
}

module.exports = router;
