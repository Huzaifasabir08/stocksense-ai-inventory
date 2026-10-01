# Production email automation

This service receives a candidate application, validates it, saves the application and an immutable CV reference in a database, then sends two messages:

1. an admin notification with the application details;
2. a candidate confirmation email with the application/reference ID.

If an invoice is created, the service generates a PDF and attaches it to the configured recipient email. Email failures are recorded separately from the saved application so a retry can be queued without creating a duplicate application or duplicate confirmation.

Required production pieces: PostgreSQL (or Supabase), private object storage for CVs, Gmail SMTP or Gmail API, a background job queue, and HTTPS deployment. Secrets belong in the server environment only.
