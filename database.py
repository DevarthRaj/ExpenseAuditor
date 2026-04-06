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

    # ── Users table ────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'client',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Claims table ───────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            employee_name TEXT NOT NULL,
            employee_email TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            justification TEXT NOT NULL,
            receipt_path TEXT,
            thumbnail_path TEXT,

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

    # ── Migrate existing claims table if columns are missing ───────────────────
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(claims)")}
    for col, definition in [
        ("user_id", "INTEGER REFERENCES users(id)"),
        ("thumbnail_path", "TEXT"),
    ]:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE claims ADD COLUMN {col} {definition}")

    conn.commit()

    # ── Seed admin user ────────────────────────────────────────────────────────
    from security import hash_password
    existing = cursor.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        """, ("admin", "admin@expenseauditor.internal", hash_password("admin123"), "admin"))
        conn.commit()
        print("[DB] ✅ Admin user seeded (admin / admin123)")

    conn.close()


# ── User CRUD ──────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str, role: str = "client") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    """, (username, email, password_hash, role))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    """Return all users, excluding password hashes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Claims CRUD ────────────────────────────────────────────────────────────────

def save_claim(data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO claims (
            user_id, employee_name, employee_email, expense_date, justification,
            receipt_path, thumbnail_path,
            merchant, amount, currency, category, city, ocr_raw,
            decision, risk_score, primary_reason, policy_snippet_used,
            flags, employee_message, auditor_note
        ) VALUES (
            :user_id, :employee_name, :employee_email, :expense_date, :justification,
            :receipt_path, :thumbnail_path,
            :merchant, :amount, :currency, :category, :city, :ocr_raw,
            :decision, :risk_score, :primary_reason, :policy_snippet_used,
            :flags, :employee_message, :auditor_note
        )
    """, {
        "user_id": data.get("user_id"),
        "employee_name": data.get("employee_name"),
        "employee_email": data.get("employee_email"),
        "expense_date": data.get("expense_date"),
        "justification": data.get("justification"),
        "receipt_path": data.get("receipt_path"),
        "thumbnail_path": data.get("thumbnail_path"),
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


def _row_to_claim(row) -> dict:
    d = dict(row)
    try:
        d["flags"] = json.loads(d["flags"]) if d["flags"] else []
    except Exception:
        d["flags"] = []
    return d


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
    return [_row_to_claim(r) for r in rows]


def get_claims_by_user(user_id: int):
    """Return only claims belonging to this user, sorted by created_at desc."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM claims WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_claim(r) for r in rows]


def get_claim_by_id(claim_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM claims WHERE id = ?", (claim_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_claim(row) if row else None


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
