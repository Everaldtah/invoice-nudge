'use strict';

/**
 * Seed script — creates a demo user, clients, and invoices.
 * Run: node src/seed.js
 */

require('dotenv').config();
const db = require('./database');
const { v4: uuidv4 } = require('uuid');
const dayjs = require('dayjs');

const userId = uuidv4();
db.prepare(`
  INSERT OR IGNORE INTO users (id, name, email, company, from_name)
  VALUES (?, 'Jane Freelancer', 'jane@example.com', 'Jane Design Co.', 'Jane')
`).run(userId);

const clients = [
  { name: 'Acme Corp', email: 'ap@acme.com', company: 'Acme Corporation' },
  { name: 'Globex Ltd', email: 'billing@globex.io', company: 'Globex Ltd' },
  { name: 'Initech Inc', email: 'finance@initech.com', company: 'Initech Inc' },
];

const clientIds = [];
for (const c of clients) {
  const cid = uuidv4();
  db.prepare('INSERT INTO clients (id, user_id, name, email, company) VALUES (?, ?, ?, ?, ?)')
    .run(cid, userId, c.name, c.email, c.company);
  clientIds.push(cid);
}

const invoices = [
  { clientIdx: 0, number: 'INV-001', amount: 3500, daysFromNow: -5 },  // 5 days overdue
  { clientIdx: 1, number: 'INV-002', amount: 8200, daysFromNow: 3 },   // due in 3 days
  { clientIdx: 2, number: 'INV-003', amount: 1200, daysFromNow: -20 }, // 20 days overdue
  { clientIdx: 0, number: 'INV-004', amount: 5000, daysFromNow: 14 },  // due in 2 weeks
];

for (const inv of invoices) {
  const dueDate = dayjs().add(inv.daysFromNow, 'day').format('YYYY-MM-DD');
  const issued = dayjs().add(inv.daysFromNow - 30, 'day').format('YYYY-MM-DD');
  db.prepare(`
    INSERT INTO invoices (id, user_id, client_id, invoice_number, amount, issued_date, due_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(uuidv4(), userId, clientIds[inv.clientIdx], inv.number, inv.amount, issued, dueDate);
}

console.log('Seed complete!');
console.log(`User ID: ${userId}`);
console.log('Now run: node src/server.js');
console.log(`Then: GET http://localhost:3000/api/dashboard/${userId}`);
