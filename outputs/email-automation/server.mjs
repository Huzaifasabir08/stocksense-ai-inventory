// Backend reference implementation. Install: npm i express zod nodemailer pdfkit
// Run this file on a server only; never expose its environment variables to the browser.
import express from "express";
import { z } from "zod";
import nodemailer from "nodemailer";
import PDFDocument from "pdfkit";

const app = express();
app.use(express.json({ limit: "2mb" }));
const input = z.object({ fullName: z.string().min(2), fatherName: z.string().min(2), cnic: z.string().regex(/^\d{5}-\d{7}-\d$/), qualification: z.string().min(2), city: z.string().min(2), email: z.string().email(), whatsapp: z.string().min(7), applicationDetails: z.string().min(2) });
const mailer = nodemailer.createTransport({ service: "gmail", auth: { user: process.env.GMAIL_USER, pass: process.env.GMAIL_APP_PASSWORD } });

function invoicePdf(referenceId, candidate) { return new Promise((resolve, reject) => { const chunks = []; const pdf = new PDFDocument(); pdf.on("data", chunk => chunks.push(chunk)); pdf.on("end", () => resolve(Buffer.concat(chunks))); pdf.on("error", reject); pdf.fontSize(20).text(process.env.COMPANY_NAME || "Company"); pdf.moveDown().fontSize(12).text(`Application reference: ${referenceId}`).text(`Candidate: ${candidate.fullName}`).text(`Date: ${new Date().toISOString().slice(0, 10)}`); pdf.end(); }); }

app.post("/api/applications", async (req, res) => {
  const parsed = input.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Please check the application details." });
  const candidate = parsed.data;
  const referenceId = `APP-${Date.now()}`;
  try {
    // Replace with a transaction in PostgreSQL/Supabase and private object-storage upload.
    await saveApplication({ ...candidate, referenceId, status: "Applied", createdAt: new Date().toISOString() });
    const details = `Reference ID: ${referenceId}\nCompany: ${process.env.COMPANY_NAME}\nCandidate: ${candidate.fullName}\nQualification: ${candidate.qualification}\nCity: ${candidate.city}\nApplication details: ${candidate.applicationDetails}`;
    await mailer.sendMail({ from: process.env.GMAIL_USER, to: process.env.ADMIN_EMAIL, subject: `New application ${referenceId}`, text: details });
    await mailer.sendMail({ from: process.env.GMAIL_USER, to: candidate.email, subject: `Application received — ${referenceId}`, text: `Dear ${candidate.fullName},\n\nWe are pleased to inform you that your job application has been successfully submitted.\n\nYour application has been received and is now under review. Our team will keep you updated regarding the next steps, interview schedule, or any additional information required.\n\nThank you for your interest and for choosing our services.\n\nBest regards,\n${process.env.COMPANY_NAME}` });
    return res.status(201).json({ referenceId, emailStatus: "sent" });
  } catch (error) {
    await recordDeliveryFailure(referenceId, String(error));
    return res.status(202).json({ referenceId, emailStatus: "queued_for_retry", message: "Application saved. Email delivery will be retried." });
  }
});

async function saveApplication(_record) { /* connect to the production database here */ }
async function recordDeliveryFailure(_referenceId, _error) { /* persist an idempotent retry job here */ }
app.listen(process.env.PORT || 3000);
