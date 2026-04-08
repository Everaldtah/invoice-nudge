'use strict';

const nodemailer = require('nodemailer');

/**
 * Send a nudge email using the user's configured SMTP settings.
 */
async function sendNudgeEmail({ smtpHost, smtpPort, smtpUser, smtpPass,
                                 fromName, fromEmail, toEmail, toName, subject, body }) {
  const transporter = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort || 587,
    secure: smtpPort === 465,
    auth: { user: smtpUser, pass: smtpPass },
  });

  await transporter.sendMail({
    from: `"${fromName}" <${fromEmail}>`,
    to: `"${toName}" <${toEmail}>`,
    subject,
    text: body,
    html: `<pre style="font-family: -apple-system, sans-serif; white-space: pre-wrap;">${body}</pre>`,
  });
}

/**
 * Test SMTP connection before saving settings.
 */
async function testSmtp({ smtpHost, smtpPort, smtpUser, smtpPass }) {
  const transporter = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort || 587,
    secure: smtpPort === 465,
    auth: { user: smtpUser, pass: smtpPass },
  });
  await transporter.verify();
  return true;
}

module.exports = { sendNudgeEmail, testSmtp };
