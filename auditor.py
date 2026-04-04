"""
Auditor module: OCR extraction + Groq-based parsing and policy auditing.
"""

import os
import json
import re
import pytesseract
from PIL import Image
from groq import Groq
from dotenv import load_dotenv
from rag import retrieve_policy

# Load .env BEFORE reading env vars — fixes module-level import ordering
load_dotenv()

# Configure tesseract path if needed (Windows)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

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


def extract_text_from_image(image_path: str) -> str:
    """Run pytesseract OCR on a receipt image and return raw text."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text.strip()
    except Exception as e:
        return f"OCR_ERROR: {str(e)}"


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


def process_claim(
    image_path: str,
    employee_name: str,
    employee_email: str,
    expense_date: str,
    justification: str,
) -> dict:
    """
    Full pipeline: OCR → parse → RAG retrieve → audit.
    Returns a merged dict ready to save to DB.
    """
    # Step 1: OCR
    ocr_raw = extract_text_from_image(image_path)

    # Step 2: Parse receipt fields with Groq
    parsed = parse_receipt_with_groq(ocr_raw, expense_date, justification)

    # Step 3: Retrieve relevant policy chunks
    query = f"{parsed.get('category', '')} {parsed.get('city', '')} expense limit"
    policy_chunks = retrieve_policy(query, n_results=4)

    # Step 4: Audit with Groq
    audit_result = audit_claim_with_groq(parsed, justification, policy_chunks)

    return {
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
