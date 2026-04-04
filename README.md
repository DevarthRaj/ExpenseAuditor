# 🧾 Policy-First Expense Auditor

An AI-powered corporate expense compliance system. Employees upload receipts, pytesseract OCR extracts the data, ChromaDB RAG retrieves relevant policy, and Groq (Llama 3.3-70B) audits the claim — all in under 10 seconds.

## Quick Start

### 1. Prerequisites
- Python 3.10+
- **Tesseract OCR** installed: [Download for Windows](https://github.com/UB-Mannheim/tesseract/wiki)
  - Add to PATH, or set path in `auditor.py` line 14

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your Groq API key
```bash
# Windows PowerShell
$env:GROQ_API_KEY = "gsk_your_key_here"

# or create a .env file
cp .env.example .env
# then edit .env
```

### 4. Generate sample policy PDF
```bash
python create_sample_policy.py
```

### 5. Run the server
```bash
python main.py
```

Open: http://localhost:8000

## Pages
| URL | Description |
|-----|-------------|
| `http://localhost:8000/` | Employee expense submission portal |
| `http://localhost:8000/dashboard` | Finance manager dashboard |

## API Routes
| Method | Path | Description |
|--------|------|-------------|
| POST | `/submit-claim` | Submit new expense claim (multipart) |
| GET | `/claims` | All claims sorted by risk score |
| GET | `/claims/{id}` | Single claim detail |
| POST | `/claims/{id}/override` | Manager override decision |

## Architecture
```
Receipt Image
     │
     ▼
pytesseract OCR (local)
     │ raw text
     ▼
Groq: Parse receipt → { merchant, date, amount, currency, category, city }
     │ category + city
     ▼
ChromaDB RAG: retrieve relevant policy chunks
     │ policy context
     ▼
Groq: Audit claim → { decision, risk_score, primary_reason, flags, ... }
     │
     ▼
SQLite: Store result → Display to employee + Finance dashboard
```

## File Structure
```
ExpenseAuditor/
├── main.py                  # FastAPI app + routes
├── auditor.py               # OCR + Groq audit pipeline
├── rag.py                   # ChromaDB + sentence-transformers RAG
├── database.py              # SQLite layer
├── create_sample_policy.py  # Generate expense_policy.pdf
├── requirements.txt
├── .env.example
├── expense_policy.pdf       # Generated policy (after running script)
├── chroma_db/               # ChromaDB vector store (auto-created)
├── uploads/                 # Receipt images (auto-created)
└── static/
    ├── employee.html        # Employee portal
    └── dashboard.html       # Finance dashboard
```
