"""
FastAPI main application for Policy-First Expense Auditor.
Run with: python main.py
"""

import os
import uuid
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

import database
import auditor
import rag

load_dotenv()

# ── Setup directories ──────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# ── Initialize DB and load policy ─────────────────────────────────────────────
database.init_db()
rag.load_policy_pdf()  # no-op if PDF not found

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Policy-First Expense Auditor",
    description="AI-powered corporate expense compliance system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve receipt images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# Serve static HTML files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Redirect root to employee portal."""
    return FileResponse("static/employee.html")


@app.get("/dashboard")
async def dashboard():
    return FileResponse("static/dashboard.html")


@app.post("/submit-claim")
async def submit_claim(
    name: str = Form(...),
    email: str = Form(...),
    date: str = Form(...),
    justification: str = Form(...),
    receipt: UploadFile = File(...),
):
    """
    Accept a new expense claim, run OCR + AI audit, store in DB.
    """
    # Save receipt file
    ext = Path(receipt.filename).suffix or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / filename

    with open(save_path, "wb") as f:
        shutil.copyfileobj(receipt.file, f)

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

    claim_id = database.save_claim(result)
    claim = database.get_claim_by_id(claim_id)
    return {"claim_id": claim_id, "claim": claim}


@app.get("/claims")
async def list_claims():
    """Return all claims sorted by risk score descending."""
    claims = database.get_all_claims()
    return {"claims": claims}


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: int):
    """Return a single claim by ID."""
    claim = database.get_claim_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


class OverrideRequest(BaseModel):
    new_decision: str
    comment: str
    override_by: str = "Manager"


@app.post("/claims/{claim_id}/override")
async def override_claim(claim_id: int, body: OverrideRequest):
    """Allow a manager to override the AI decision."""
    claim = database.get_claim_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if body.new_decision not in ("APPROVED", "FLAGGED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Invalid decision value")
    database.override_claim(claim_id, body.new_decision, body.comment, body.override_by)
    return {"success": True, "claim_id": claim_id, "new_decision": body.new_decision}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
