'use strict';

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');

const invoicesRouter = require('./routes/invoices');
const clientsRouter = require('./routes/clients');
const usersRouter = require('./routes/users');
const sequencesRouter = require('./routes/sequences');
const { startNudgeScheduler } = require('./jobs/nudge-scheduler');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json());

// Routes
app.use('/api/users', usersRouter);
app.use('/api/clients', clientsRouter);
app.use('/api/invoices', invoicesRouter);
app.use('/api/sequences', sequencesRouter);

// Dashboard summary endpoint
app.get('/api/dashboard/:userId', (req, res) => {
  const db = require('./database');
  const { userId } = req.params;

  const stats = db.prepare(`
    SELECT
      COUNT(*) as total,
      SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
      SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END) as overdue,
      SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid,
      SUM(CASE WHEN status != 'paid' AND status != 'cancelled' THEN amount ELSE 0 END) as outstanding_amount,
      SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) as collected_amount
    FROM invoices WHERE user_id = ?
  `).get(userId);

  const recentNudges = db.prepare(`
    SELECT nl.sent_at, nl.status, i.invoice_number, c.name as client_name, ns.subject_template
    FROM nudge_logs nl
    JOIN invoices i ON nl.invoice_id = i.id
    JOIN clients c ON i.client_id = c.id
    JOIN nudge_steps ns ON nl.step_id = ns.id
    WHERE i.user_id = ?
    ORDER BY nl.sent_at DESC
    LIMIT 10
  `).all(userId);

  res.json({ stats, recentNudges });
});

app.get('/', (req, res) => {
  res.json({
    name: 'Invoice Nudge',
    version: '1.0.0',
    description: 'Smart invoice follow-up automation',
    docs: '/api/docs',
    endpoints: [
      'GET  /api/dashboard/:userId',
      'POST /api/users',
      'GET  /api/clients?userId=',
      'POST /api/clients',
      'GET  /api/invoices?userId=',
      'POST /api/invoices',
      'PUT  /api/invoices/:id/mark-paid',
      'GET  /api/sequences?userId=',
      'POST /api/sequences',
    ]
  });
});

app.get('/health', (req, res) => res.json({ status: 'ok', ts: new Date().toISOString() }));

// Start cron scheduler
startNudgeScheduler();

app.listen(PORT, () => {
  console.log(`Invoice Nudge running on http://localhost:${PORT}`);
  console.log(`Nudge scheduler active — checking every hour`);
});

module.exports = app;
