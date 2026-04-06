"""
FastAPI main application for Policy-First Expense Auditor.
Run with: python main.py
"""

import io
import os
import uuid
import shutil
from pathlib import Path

import fitz  # PyMuPDF — for PDF thumbnail generation
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image

import database
import auditor
import rag
from security import hash_password, verify_password
from auth import (
    create_token,
    get_current_user,
    require_admin,
)

load_dotenv()

# ── Setup directories ──────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# ── Initialize DB and load policy ─────────────────────────────────────────────
database.init_db()
rag.load_policy_pdf(force_reload=True)

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Policy-First Expense Auditor",
    description="AI-powered corporate expense compliance system",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── PDF thumbnail helper ───────────────────────────────────────────────────────

def generate_pdf_thumbnail(pdf_path: str, out_dir: Path) -> str | None:
    """
    Render page 1 of a PDF as a PNG thumbnail.
    Returns the saved thumbnail filename (relative), or None on failure.
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(1.5, 1.5)          # ~108 DPI — good for preview
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        doc.close()

        stem = Path(pdf_path).stem
        thumb_name = f"{stem}_thumb.png"
        thumb_path = out_dir / thumb_name
        pix.save(str(thumb_path))
        return thumb_name
    except Exception as e:
        print(f"[Thumbnail] Failed to generate thumbnail for {pdf_path}: {e}")
        return None


# ── Page routes ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root redirects to login page."""
    return FileResponse("static/login.html")


@app.get("/portal")
async def portal():
    """Employee portal."""
    return FileResponse("static/employee.html")


@app.get("/dashboard")
async def dashboard():
    """Admin finance dashboard."""
    return FileResponse("static/dashboard.html")


# ── Auth routes ────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
async def register(body: RegisterRequest):
    """Register a new client account."""
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if database.get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if database.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = hash_password(body.password)
    user_id = database.create_user(body.username.strip(), body.email.strip(), hashed, role="client")
    token = create_token(user_id, body.username, "client")
    return {"token": token, "role": "client", "username": body.username, "user_id": user_id}


@app.post("/auth/login")
async def login(body: LoginRequest):
    """Login and return a JWT token."""
    user = database.get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(user["id"], user["username"], user["role"])
    return {"token": token, "role": user["role"], "username": user["username"], "user_id": user["id"], "email": user["email"]}


@app.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Return current logged-in user info."""
    return {
        "user_id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user["role"],
    }


# ── Claim submission (clients only, attach user_id) ───────────────────────────

@app.post("/submit-claim")
async def submit_claim(
    name: str = Form(...),
    email: str = Form(...),
    date: str = Form(...),
    justification: str = Form(...),
    receipt: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Accept a new expense claim, run OCR + AI audit, store in DB."""
    ext = Path(receipt.filename).suffix.lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / filename

    with open(save_path, "wb") as f:
        shutil.copyfileobj(receipt.file, f)

    # Generate thumbnail for PDFs
    thumbnail_path = None
    if ext == ".pdf":
        thumb_name = generate_pdf_thumbnail(str(save_path), UPLOAD_DIR)
        if thumb_name:
            thumbnail_path = str(UPLOAD_DIR / thumb_name)

    try:
        result = auditor.process_claim(
            image_path=str(save_path),
            employee_name=name,
            employee_email=email,
            expense_date=date,
            justification=justification,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

    result["user_id"] = current_user["id"]
    result["thumbnail_path"] = thumbnail_path

    claim_id = database.save_claim(result)
    claim = database.get_claim_by_id(claim_id)
    return {"claim_id": claim_id, "claim": claim}


# ── Client: my claims ─────────────────────────────────────────────────────────

@app.get("/my-claims")
async def my_claims(current_user: dict = Depends(get_current_user)):
    """Return only the logged-in user's claims."""
    claims = database.get_claims_by_user(current_user["id"])
    return {"claims": claims}


# ── Admin: all claims ─────────────────────────────────────────────────────────

@app.get("/claims")
async def list_claims(admin: dict = Depends(require_admin)):
    """Return all claims sorted by risk score descending. Admin only."""
    claims = database.get_all_claims()
    return {"claims": claims}


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: int, current_user: dict = Depends(get_current_user)):
    """Return a single claim by ID. Admin sees any; clients can only see their own."""
    claim = database.get_claim_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if current_user["role"] != "admin" and claim.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return claim


# ── Admin: override ───────────────────────────────────────────────────────────

class OverrideRequest(BaseModel):
    new_decision: str
    comment: str
    override_by: str = "Admin"


@app.post("/claims/{claim_id}/override")
async def override_claim(
    claim_id: int,
    body: OverrideRequest,
    admin: dict = Depends(require_admin),
):
    """Allow admin to override the AI decision."""
    claim = database.get_claim_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if body.new_decision not in ("APPROVED", "FLAGGED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Invalid decision value")
    database.override_claim(claim_id, body.new_decision, body.comment, admin["username"])
    return {"success": True, "claim_id": claim_id, "new_decision": body.new_decision}


@app.post("/reload-policy")
async def reload_policy(admin: dict = Depends(require_admin)):
    """Admin endpoint: re-ingest the policy PDF into ChromaDB."""
    rag.load_policy_pdf(force_reload=True)
    import rag as _rag
    count = _rag._get_collection().count()
    return {"success": True, "chunks_loaded": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
