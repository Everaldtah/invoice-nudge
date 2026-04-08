'use strict';

const express = require('express');
const { v4: uuidv4 } = require('uuid');
const db = require('../database');

const router = express.Router();

router.post('/', (req, res) => {
  const { name, email, company, smtpHost, smtpPort, smtpUser, smtpPass, fromName } = req.body;
  if (!name || !email) return res.status(400).json({ error: 'name and email required' });

  const existing = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
  if (existing) return res.status(409).json({ error: 'Email already registered', userId: existing.id });

  const id = uuidv4();
  db.prepare(`
    INSERT INTO users (id, name, email, company, smtp_host, smtp_port, smtp_user, smtp_pass, from_name)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(id, name, email, company, smtpHost, smtpPort || 587, smtpUser, smtpPass, fromName || name);

  res.status(201).json({ id, name, email, company });
});

router.get('/:id', (req, res) => {
  const user = db.prepare('SELECT id, name, email, company, from_name, created_at FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: 'Not found' });
  res.json(user);
});

router.put('/:id/smtp', (req, res) => {
  const { smtpHost, smtpPort, smtpUser, smtpPass, fromName } = req.body;
  db.prepare('UPDATE users SET smtp_host=?, smtp_port=?, smtp_user=?, smtp_pass=?, from_name=? WHERE id=?')
    .run(smtpHost, smtpPort, smtpUser, smtpPass, fromName, req.params.id);
  res.json({ success: true });
});

module.exports = router;
