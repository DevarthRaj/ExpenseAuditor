import sqlite3
import json
from datetime import datetime
from typing import Optional

DB_PATH = "expense_auditor.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_name TEXT NOT NULL,
            employee_email TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            justification TEXT NOT NULL,
            receipt_path TEXT,

            -- OCR extracted fields
            merchant TEXT,
            amount REAL,
            currency TEXT,
            category TEXT,
            city TEXT,
            ocr_raw TEXT,

            -- Audit result
            decision TEXT,
            risk_score REAL,
            primary_reason TEXT,
            policy_snippet_used TEXT,
            flags TEXT,
            employee_message TEXT,
            auditor_note TEXT,

            -- Override
            override_decision TEXT,
            override_comment TEXT,
            override_by TEXT,
            override_at TEXT,

            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_claim(data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO claims (
            employee_name, employee_email, expense_date, justification, receipt_path,
            merchant, amount, currency, category, city, ocr_raw,
            decision, risk_score, primary_reason, policy_snippet_used,
            flags, employee_message, auditor_note
        ) VALUES (
            :employee_name, :employee_email, :expense_date, :justification, :receipt_path,
            :merchant, :amount, :currency, :category, :city, :ocr_raw,
            :decision, :risk_score, :primary_reason, :policy_snippet_used,
            :flags, :employee_message, :auditor_note
        )
    """, {
        "employee_name": data.get("employee_name"),
        "employee_email": data.get("employee_email"),
        "expense_date": data.get("expense_date"),
        "justification": data.get("justification"),
        "receipt_path": data.get("receipt_path"),
        "merchant": data.get("merchant"),
        "amount": data.get("amount"),
        "currency": data.get("currency", "USD"),
        "category": data.get("category"),
        "city": data.get("city"),
        "ocr_raw": data.get("ocr_raw"),
        "decision": data.get("decision"),
        "risk_score": data.get("risk_score"),
        "primary_reason": data.get("primary_reason"),
        "policy_snippet_used": data.get("policy_snippet_used"),
        "flags": json.dumps(data.get("flags", [])),
        "employee_message": data.get("employee_message"),
        "auditor_note": data.get("auditor_note"),
    })
    claim_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return claim_id


def get_all_claims():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM claims
        ORDER BY
            CASE WHEN override_decision IS NOT NULL THEN override_decision ELSE decision END,
            risk_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["flags"] = json.loads(d["flags"]) if d["flags"] else []
        except Exception:
            d["flags"] = []
        result.append(d)
    return result


def get_claim_by_id(claim_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM claims WHERE id = ?", (claim_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["flags"] = json.loads(d["flags"]) if d["flags"] else []
    except Exception:
        d["flags"] = []
    return d


def override_claim(claim_id: int, new_decision: str, comment: str, override_by: str = "Manager"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE claims
        SET override_decision = ?,
            override_comment = ?,
            override_by = ?,
            override_at = ?
        WHERE id = ?
    """, (new_decision, comment, override_by, datetime.utcnow().isoformat(), claim_id))
    conn.commit()
    conn.close()
