'use strict';

const cron = require('node-cron');
const dayjs = require('dayjs');
const { v4: uuidv4 } = require('uuid');
const db = require('../database');
const { sendNudgeEmail } = require('../services/mailer');

/**
 * Runs every hour, checks for invoices that should receive a nudge based on
 * the assigned nudge sequence steps.
 */
function startNudgeScheduler() {
  // Run at the top of every hour
  cron.schedule('0 * * * *', async () => {
    console.log(`[nudge-scheduler] Running at ${new Date().toISOString()}`);
    await processNudges();
  });

  // Also run once on startup (after 5 seconds)
  setTimeout(async () => {
    console.log('[nudge-scheduler] Initial run on startup');
    await processNudges();
  }, 5000);
}

async function processNudges() {
  const today = dayjs().format('YYYY-MM-DD');

  // Get all unpaid invoices with their user's default sequence
  const invoices = db.prepare(`
    SELECT i.*, u.smtp_host, u.smtp_port, u.smtp_user, u.smtp_pass, u.from_name,
           u.email as user_email, c.name as client_name, c.email as client_email,
           c.avg_days_to_pay
    FROM invoices i
    JOIN users u ON i.user_id = u.id
    JOIN clients c ON i.client_id = c.id
    WHERE i.status IN ('pending', 'overdue')
  `).all();

  for (const invoice of invoices) {
    try {
      await processInvoiceNudges(invoice, today);
    } catch (err) {
      console.error(`[nudge-scheduler] Error for invoice ${invoice.id}:`, err.message);
    }
  }
}

async function processInvoiceNudges(invoice, today) {
  const daysFromDue = dayjs(today).diff(dayjs(invoice.due_date), 'day');

  // Get the user's default sequence
  const seq = db.prepare(`
    SELECT ns.* FROM nudge_sequences ns WHERE ns.user_id = ? AND ns.is_default = 1
  `).get(invoice.user_id);

  if (!seq) return;

  const steps = db.prepare(`
    SELECT * FROM nudge_steps WHERE sequence_id = ? ORDER BY step_number
  `).all(seq.id);

  for (const step of steps) {
    // Check if this step should fire today
    if (step.days_after_due !== daysFromDue) continue;

    // Check if this nudge was already sent for this invoice
    const alreadySent = db.prepare(`
      SELECT id FROM nudge_logs WHERE invoice_id = ? AND step_id = ? AND status = 'sent'
    `).get(invoice.id, step.id);

    if (alreadySent) continue;

    // Render templates
    const context = {
      '{{invoice_number}}': invoice.invoice_number,
      '{{client_name}}': invoice.client_name,
      '{{amount}}': Number(invoice.amount).toFixed(2),
      '{{currency}}': invoice.currency,
      '{{due_date}}': invoice.due_date,
      '{{days_overdue}}': Math.max(0, daysFromDue).toString(),
      '{{sender_name}}': invoice.from_name || 'Your Service Provider',
      '{{payment_link_text}}': invoice.payment_link
        ? `Pay now: ${invoice.payment_link}`
        : 'Please send payment via your usual method.',
    };

    const subject = renderTemplate(step.subject_template, context);
    const body = renderTemplate(step.body_template, context);

    const logId = uuidv4();
    try {
      if (invoice.smtp_host && invoice.smtp_user) {
        await sendNudgeEmail({
          smtpHost: invoice.smtp_host,
          smtpPort: invoice.smtp_port,
          smtpUser: invoice.smtp_user,
          smtpPass: invoice.smtp_pass,
          fromName: invoice.from_name,
          fromEmail: invoice.user_email,
          toEmail: invoice.client_email,
          toName: invoice.client_name,
          subject,
          body,
        });
        console.log(`[nudge] Sent step ${step.step_number} for invoice ${invoice.invoice_number} to ${invoice.client_email}`);
        db.prepare('INSERT INTO nudge_logs (id, invoice_id, step_id, status) VALUES (?, ?, ?, \'sent\')')
          .run(logId, invoice.id, step.id);
      } else {
        // Log as dry-run when SMTP not configured
        console.log(`[nudge-dryrun] Would send "${subject}" to ${invoice.client_email}`);
        db.prepare('INSERT INTO nudge_logs (id, invoice_id, step_id, status, error) VALUES (?, ?, ?, \'skipped\', \'SMTP not configured\')')
          .run(logId, invoice.id, step.id);
      }
    } catch (err) {
      db.prepare('INSERT INTO nudge_logs (id, invoice_id, step_id, status, error) VALUES (?, ?, ?, \'failed\', ?)')
        .run(logId, invoice.id, step.id, err.message);
    }
  }
}

function renderTemplate(template, context) {
  let result = template;
  for (const [key, value] of Object.entries(context)) {
    result = result.split(key).join(value);
  }
  return result;
}

module.exports = { startNudgeScheduler, processNudges };
