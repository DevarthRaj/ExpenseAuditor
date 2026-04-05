"""
Auditor module: OCR extraction + Groq-based parsing and policy auditing.
Supports both image files and PDF receipts.
"""

import os
import io
import json
import re
import smtplib
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import fitz  # PyMuPDF — used for PDF-to-image conversion AND PDF text extraction
import pytesseract
from PIL import Image
from groq import Groq
from dotenv import load_dotenv
from rag import retrieve_policy

# Load .env BEFORE reading env vars — fixes module-level import ordering
load_dotenv()

# Configure tesseract path (Windows)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

MODEL = "llama-3.3-70b-versatile"
_client = None


def get_client() -> Groq:
    """Lazily initialize the Groq client so load_dotenv() always runs first."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Create a .env file with GROQ_API_KEY=your_key or set the environment variable."
            )
        _client = Groq(api_key=api_key)
    return _client


# ── OCR ───────────────────────────────────────────────────────────────────────

def _extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF receipt.
    Strategy:
      1. Try PyMuPDF direct text extraction (fast, works for text-based PDFs).
      2. If little/no text found, render each page to image and run Tesseract OCR.
    """
    try:
        doc = fitz.open(pdf_path)
        all_text = []

        for page in doc:
            # Try direct text extraction first
            page_text = page.get_text("text").strip()
            if page_text:
                all_text.append(page_text)
            else:
                # Render page to image at 200 DPI and OCR it
                mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                ocr_text = pytesseract.image_to_string(img, config="--psm 6")
                if ocr_text.strip():
                    all_text.append(ocr_text.strip())

        doc.close()
        result = "\n\n".join(all_text).strip()
        return result if result else "No text could be extracted from PDF."
    except Exception as e:
        return f"PDF_OCR_ERROR: {str(e)}"


def extract_text_from_image(image_path: str) -> str:
    """
    Run OCR on a receipt file. Handles both image files and PDFs.
    For PDFs: uses PyMuPDF for direct text extraction + Tesseract fallback.
    For images: uses Tesseract directly.
    """
    path = Path(image_path)
    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            return _extract_text_from_pdf(image_path)
        else:
            # Standard image path (PNG, JPG, JPEG, WEBP, TIFF, BMP, etc.)
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, config="--psm 6")
            return text.strip()
    except Exception as e:
        return f"OCR_ERROR: {str(e)}"


# ── Receipt parsing ───────────────────────────────────────────────────────────

def parse_receipt_with_groq(ocr_text: str, expense_date: str, justification: str) -> dict:
    """
    Use Groq to extract structured fields from OCR text.
    Returns: merchant, date, amount, currency, category, city
    """
    system_prompt = """You are a receipt parser. Extract structured data from OCR text from a receipt.
Return ONLY a valid JSON object with these exact keys:
{
  "merchant": "string (business name)",
  "date": "string (YYYY-MM-DD format, use expense_date if unclear)",
  "amount": number (total amount as float, 0 if not found),
  "currency": "string (3-letter code, default USD)",
  "category": "string (one of: Meals, Travel, Lodging, Entertainment, Office Supplies, Software, Other)",
  "city": "string (city name if detectable, else 'Unknown')"
}
No markdown fences, no explanation, only the JSON object."""

    user_content = f"""OCR Text from receipt:
\"\"\"
{ocr_text}
\"\"\"

Employee-provided date: {expense_date}
Business justification: {justification}

Extract the structured data. Use employee-provided date if receipt date is unclear."""

    resp = get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content.strip()
    # Strip any accidental markdown fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "merchant": "Unknown",
            "date": expense_date,
            "amount": 0.0,
            "currency": "USD",
            "category": "Other",
            "city": "Unknown",
        }


# ── Audit ─────────────────────────────────────────────────────────────────────

def audit_claim_with_groq(
    parsed: dict,
    justification: str,
    policy_chunks: list[str],
) -> dict:
    """
    Use Groq to audit the claim against retrieved policy chunks.
    Returns a decision JSON dict.
    """
    policy_text = "\n\n---\n\n".join(policy_chunks) if policy_chunks else "No policy found."

    system_prompt = """You are a strict corporate expense auditor AI.
Your job is to audit employee expense claims against company T&E policy.

DECISION RULES:
- APPROVED: expense is within limits, purpose is clear and appropriate, no policy violations
- FLAGGED: borderline amount (within 10% of limit), vague justification, weekend expense, unusual category for city
- REJECTED: amount exceeds limit, prohibited items (alcohol, entertainment without approval), purpose contradicts receipt merchant/category

STRICT RULES:
1. Never hallucinate policy rules. Only use the policy chunks provided.
2. If no relevant policy chunks are available, set decision to FLAGGED with reason "No matching policy found for this category/city."
3. Return ONLY a valid JSON object. No markdown fences, no explanation outside JSON.
4. primary_reason MUST cite exact amounts. Example: "NYC meal limit is $50/person, claim is $67."
5. risk_score is a float from 0.0 (no risk) to 1.0 (max risk). APPROVED <= 0.3, FLAGGED 0.3-0.7, REJECTED >= 0.7
6. flags is an array of short string tags like ["weekend_expense", "exceeds_limit", "vague_purpose"]
7. employee_message is a friendly, concise message shown to the employee.
8. auditor_note is a detailed note for the finance manager.

Return this exact JSON structure:
{
  "decision": "APPROVED" | "FLAGGED" | "REJECTED",
  "risk_score": float,
  "primary_reason": "string",
  "policy_snippet_used": "string (the most relevant policy sentence quoted)",
  "flags": ["string"],
  "employee_message": "string",
  "auditor_note": "string"
}"""

    user_content = f"""EXPENSE CLAIM DETAILS:
- Merchant: {parsed.get('merchant')}
- Date: {parsed.get('date')}
- Amount: {parsed.get('currency', 'USD')} {parsed.get('amount')}
- Category: {parsed.get('category')}
- City: {parsed.get('city')}
- Business Justification: {justification}

RETRIEVED POLICY CHUNKS:
{policy_text}

Audit this expense claim against the policy and return the JSON decision."""

    resp = get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=700,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "decision": "FLAGGED",
            "risk_score": 0.5,
            "primary_reason": "Audit system could not parse AI response. Manual review required.",
            "policy_snippet_used": "",
            "flags": ["parse_error"],
            "employee_message": "Your claim has been flagged for manual review.",
            "auditor_note": f"Raw AI response could not be parsed as JSON: {raw[:300]}",
        }


# ── Email notification ────────────────────────────────────────────────────────

def _build_email_html(result: dict) -> str:
    """Build a styled HTML email body for the audit result notification."""
    decision = result.get("decision", "UNKNOWN")
    employee_name = result.get("employee_name", "Employee")
    employee_message = result.get("employee_message", "")
    merchant = result.get("merchant", "Unknown")
    amount = result.get("amount", 0)
    currency = result.get("currency", "USD")
    category = result.get("category", "Unknown")
    expense_date = result.get("expense_date", "")
    risk_score = result.get("risk_score", 0)
    policy_snippet = result.get("policy_snippet_used", "")
    flags = result.get("flags", [])

    decision_colors = {
        "APPROVED": {"bg": "#d4edda", "border": "#28a745", "text": "#155724", "icon": "✅"},
        "FLAGGED":  {"bg": "#fff3cd", "border": "#ffc107", "text": "#856404", "icon": "⚠️"},
        "REJECTED": {"bg": "#f8d7da", "border": "#dc3545", "text": "#721c24", "icon": "❌"},
    }
    colors = decision_colors.get(decision, {"bg": "#e2e3e5", "border": "#6c757d", "text": "#383d41", "icon": "ℹ️"})

    flags_html = "".join(
        f'<span style="display:inline-block;background:#6c757d;color:#fff;border-radius:4px;'
        f'padding:2px 8px;font-size:12px;margin:2px;">{f}</span>'
        for f in flags
    ) if flags else "<em>None</em>"

    policy_html = (
        f'<blockquote style="border-left:3px solid #6c757d;margin:10px 0;padding:8px 12px;'
        f'background:#f8f9fa;font-style:italic;font-size:13px;color:#555;">'
        f'"{policy_snippet}"</blockquote>'
    ) if policy_snippet else ""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;
              box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden;">

    <!-- Header -->
    <div style="background:#1a237e;padding:24px 28px;">
      <h1 style="color:#fff;margin:0;font-size:20px;">Acme Corp — Expense Audit Result</h1>
      <p style="color:#c5cae9;margin:6px 0 0;">Automated notification from the Expense Auditor System</p>
    </div>

    <!-- Decision Banner -->
    <div style="background:{colors['bg']};border-left:5px solid {colors['border']};
                padding:16px 24px;margin:0;">
      <h2 style="color:{colors['text']};margin:0;font-size:18px;">
        {colors['icon']} Decision: {decision}
      </h2>
    </div>

    <!-- Body -->
    <div style="padding:24px 28px;">
      <p style="font-size:15px;color:#333;">Dear <strong>{employee_name}</strong>,</p>
      <p style="font-size:14px;color:#555;line-height:1.6;">{employee_message}</p>

      <!-- Claim Summary -->
      <h3 style="color:#1a237e;border-bottom:1px solid #e0e0e0;padding-bottom:6px;">Claim Summary</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr style="background:#f5f5f5;">
          <td style="padding:8px 12px;font-weight:bold;width:140px;">Merchant</td>
          <td style="padding:8px 12px;">{merchant}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;font-weight:bold;">Amount</td>
          <td style="padding:8px 12px;">{currency} {amount}</td>
        </tr>
        <tr style="background:#f5f5f5;">
          <td style="padding:8px 12px;font-weight:bold;">Category</td>
          <td style="padding:8px 12px;">{category}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;font-weight:bold;">Date</td>
          <td style="padding:8px 12px;">{expense_date}</td>
        </tr>
        <tr style="background:#f5f5f5;">
          <td style="padding:8px 12px;font-weight:bold;">Risk Score</td>
          <td style="padding:8px 12px;">{int(risk_score * 100)}%</td>
        </tr>
      </table>

      <!-- Flags -->
      <h3 style="color:#1a237e;border-bottom:1px solid #e0e0e0;padding-bottom:6px;margin-top:20px;">Flags</h3>
      <div style="padding:4px 0;">{flags_html}</div>

      <!-- Policy Reference -->
      {f'<h3 style="color:#1a237e;border-bottom:1px solid #e0e0e0;padding-bottom:6px;margin-top:20px;">Relevant Policy</h3>{policy_html}' if policy_snippet else ''}

      <!-- Footer note -->
      <p style="font-size:12px;color:#888;margin-top:28px;border-top:1px solid #eee;padding-top:12px;">
        If you believe this decision is incorrect, please contact your manager or reach out to
        <a href="mailto:finance-help@acmecorp.com" style="color:#1a237e;">finance-help@acmecorp.com</a>.<br>
        This is an automated message — please do not reply directly to this email.
      </p>
    </div>
  </div>
</body>
</html>
"""


def send_audit_email(result: dict) -> bool:
    """
    Send the audit result email to the employee.
    Uses SMTP credentials from environment variables.

    Required env vars:
      SMTP_HOST     (e.g. smtp.gmail.com)
      SMTP_PORT     (e.g. 587)
      SMTP_USER     (sender email address)
      SMTP_PASSWORD (sender password / app password)
      SMTP_FROM     (optional display name, defaults to SMTP_USER)

    Returns True on success, False on failure (logs error but never raises).
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not all([smtp_host, smtp_user, smtp_password]):
        print(
            "[Email] SMTP not configured (SMTP_HOST / SMTP_USER / SMTP_PASSWORD missing). "
            "Skipping email notification."
        )
        return False

    to_email = result.get("employee_email", "")
    if not to_email:
        print("[Email] No employee email found in result. Skipping.")
        return False

    decision = result.get("decision", "UNKNOWN")
    employee_name = result.get("employee_name", "Employee")

    subject_map = {
        "APPROVED": f"✅ Your Expense Claim Has Been Approved — {employee_name}",
        "FLAGGED":  f"⚠️ Your Expense Claim Requires Attention — {employee_name}",
        "REJECTED": f"❌ Your Expense Claim Has Been Rejected — {employee_name}",
    }
    subject = subject_map.get(decision, f"Expense Claim Update — {employee_name}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    # Plain text fallback
    plain_text = (
        f"Hello {employee_name},\n\n"
        f"Your expense claim audit result: {decision}\n\n"
        f"{result.get('employee_message', '')}\n\n"
        f"Merchant: {result.get('merchant', 'N/A')}\n"
        f"Amount: {result.get('currency', 'USD')} {result.get('amount', 0)}\n"
        f"Date: {result.get('expense_date', 'N/A')}\n\n"
        f"For questions, contact finance-help@acmecorp.com\n"
    )
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(_build_email_html(result), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
        print(f"[Email] ✅ Audit result ({decision}) sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Email] ❌ Failed to send email to {to_email}: {e}")
        return False


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_claim(
    image_path: str,
    employee_name: str,
    employee_email: str,
    expense_date: str,
    justification: str,
) -> dict:
    """
    Full pipeline: OCR → parse → RAG retrieve → audit → email notification.
    Returns a merged dict ready to save to DB.
    """
    # Step 1: OCR (supports images + PDFs)
    ocr_raw = extract_text_from_image(image_path)
    print(f"[OCR] Extracted {len(ocr_raw)} chars from {Path(image_path).name}")

    # Step 2: Parse receipt fields with Groq
    parsed = parse_receipt_with_groq(ocr_raw, expense_date, justification)
    print(f"[Parse] Merchant={parsed.get('merchant')} Amount={parsed.get('amount')} City={parsed.get('city')}")

    # Step 3: Retrieve relevant policy chunks (broader query for better RAG recall)
    query = (
        f"{parsed.get('category', '')} {parsed.get('city', '')} expense limit receipt requirement"
    )
    policy_chunks = retrieve_policy(query, n_results=5)
    print(f"[RAG] Retrieved {len(policy_chunks)} policy chunks for query: {query!r}")

    # Step 4: Audit with Groq
    audit_result = audit_claim_with_groq(parsed, justification, policy_chunks)
    print(f"[Audit] Decision={audit_result.get('decision')} Risk={audit_result.get('risk_score')}")

    result = {
        "employee_name": employee_name,
        "employee_email": employee_email,
        "expense_date": expense_date,
        "justification": justification,
        "receipt_path": image_path,
        "ocr_raw": ocr_raw,
        "merchant": parsed.get("merchant"),
        "amount": parsed.get("amount"),
        "currency": parsed.get("currency", "USD"),
        "category": parsed.get("category"),
        "city": parsed.get("city"),
        "decision": audit_result.get("decision"),
        "risk_score": audit_result.get("risk_score"),
        "primary_reason": audit_result.get("primary_reason"),
        "policy_snippet_used": audit_result.get("policy_snippet_used"),
        "flags": audit_result.get("flags", []),
        "employee_message": audit_result.get("employee_message"),
        "auditor_note": audit_result.get("auditor_note"),
    }

    # Step 5: Send email notification to employee
    send_audit_email(result)

    return result
