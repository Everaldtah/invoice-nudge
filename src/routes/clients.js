'use strict';

const express = require('express');
const { v4: uuidv4 } = require('uuid');
const db = require('../database');

const router = express.Router();

router.get('/', (req, res) => {
  const { userId } = req.query;
  if (!userId) return res.status(400).json({ error: 'userId required' });
  const clients = db.prepare(`
    SELECT c.*,
      COUNT(i.id) as invoice_count,
      SUM(CASE WHEN i.status = 'paid' THEN i.amount ELSE 0 END) as total_paid,
      SUM(CASE WHEN i.status IN ('pending','overdue') THEN i.amount ELSE 0 END) as total_outstanding
    FROM clients c
    LEFT JOIN invoices i ON c.id = i.client_id
    WHERE c.user_id = ?
    GROUP BY c.id
    ORDER BY c.name
  `).all(userId);
  res.json(clients);
});

router.post('/', (req, res) => {
  const { userId, name, email, company, notes } = req.body;
  if (!userId || !name || !email) return res.status(400).json({ error: 'userId, name, email required' });
  const id = uuidv4();
  db.prepare('INSERT INTO clients (id, user_id, name, email, company, notes) VALUES (?, ?, ?, ?, ?, ?)')
    .run(id, userId, name, email, company, notes);
  res.status(201).json(db.prepare('SELECT * FROM clients WHERE id = ?').get(id));
});

router.get('/:id', (req, res) => {
  const client = db.prepare('SELECT * FROM clients WHERE id = ?').get(req.params.id);
  if (!client) return res.status(404).json({ error: 'Not found' });
  const invoices = db.prepare('SELECT * FROM invoices WHERE client_id = ? ORDER BY due_date DESC').all(client.id);
  res.json({ ...client, invoices });
});

router.put('/:id', (req, res) => {
  const { name, email, company, notes } = req.body;
  db.prepare('UPDATE clients SET name = ?, email = ?, company = ?, notes = ? WHERE id = ?')
    .run(name, email, company, notes, req.params.id);
  res.json(db.prepare('SELECT * FROM clients WHERE id = ?').get(req.params.id));
});

module.exports = router;
