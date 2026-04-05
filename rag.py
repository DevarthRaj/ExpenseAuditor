"""
RAG module: loads policy PDF into ChromaDB and retrieves relevant chunks.
Uses sentence-transformers (all-MiniLM-L6-v2) for embedding.
"""

import os
import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "expense_policy"
POLICY_PDF = "expense_policy.pdf"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    _client = chromadb.PersistentClient(path=CHROMA_PATH)
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def load_policy_pdf(pdf_path: str = POLICY_PDF, force_reload: bool = False):
    """
    Parse the policy PDF, chunk it, and upsert into ChromaDB.
    Call this once (or whenever the policy changes).
    If force_reload=True, clears the collection first to ensure fresh data.
    """
    if not os.path.exists(pdf_path):
        print(f"[RAG] Policy PDF not found at {pdf_path}. Skipping load.")
        return

    collection = _get_collection()

    # If force_reload, delete all existing documents from the collection
    if force_reload and collection.count() > 0:
        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            print(f"[RAG] Cleared {len(existing['ids'])} existing chunks from ChromaDB.")

    doc = fitz.open(pdf_path)
    chunks = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        if not text:
            continue

        # Use smaller chunks (200 chars) with overlap to improve retrieval precision
        step = 200
        overlap = 60
        start = 0
        while start < len(text):
            end = start + step
            chunk = text[start:end].strip()
            if len(chunk) > 20:  # skip tiny fragments
                chunks.append({
                    "id": f"page{page_num}_s{start}",
                    "text": chunk,
                    "metadata": {"page": page_num, "start": start}
                })
            start += step - overlap

    if not chunks:
        print("[RAG] No text extracted from PDF.")
        return

    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"[RAG] Loaded {len(chunks)} chunks from {pdf_path} into ChromaDB.")


def retrieve_policy(query: str, n_results: int = 5) -> list[str]:
    """
    Retrieve the top-n most relevant policy chunks for a query.
    Returns a list of text strings.
    """
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    n_results = min(n_results, count)
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )
    docs = results.get("documents", [[]])[0]
    return docs
