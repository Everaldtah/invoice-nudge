'use strict';

const express = require('express');
const { v4: uuidv4 } = require('uuid');
const db = require('../database');

const router = express.Router();

router.get('/', (req, res) => {
  const { userId } = req.query;
  if (!userId) return res.status(400).json({ error: 'userId required' });
  const seqs = db.prepare('SELECT * FROM nudge_sequences WHERE user_id = ?').all(userId);
  const result = seqs.map(s => ({
    ...s,
    steps: db.prepare('SELECT * FROM nudge_steps WHERE sequence_id = ? ORDER BY step_number').all(s.id)
  }));
  res.json(result);
});

router.post('/', (req, res) => {
  const { userId, name, steps = [] } = req.body;
  if (!userId || !name) return res.status(400).json({ error: 'userId and name required' });
  const id = uuidv4();
  db.prepare('INSERT INTO nudge_sequences (id, user_id, name) VALUES (?, ?, ?)').run(id, userId, name);
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    db.prepare(`
      INSERT INTO nudge_steps (id, sequence_id, step_number, days_after_due, subject_template, body_template)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(uuidv4(), id, i + 1, s.daysAfterDue, s.subject, s.body);
  }
  res.status(201).json({ id, name, steps: db.prepare('SELECT * FROM nudge_steps WHERE sequence_id = ?').all(id) });
});

module.exports = router;
