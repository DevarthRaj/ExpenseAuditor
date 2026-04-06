"""
RAG module: loads policy PDF into ChromaDB and retrieves relevant chunks.
Uses sentence-transformers (all-MiniLM-L6-v2) for embedding.
"""

import os
import logging
import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions

# Suppress noisy ChromaDB telemetry errors
logging.getLogger("chromadb").setLevel(logging.ERROR)

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
    Only reloads if force_reload=True — set that only when policy PDF changes.
    """
    if not os.path.exists(pdf_path):
        print(f"[RAG] Policy PDF not found at {pdf_path}. Skipping load.")
        return

    collection = _get_collection()

    # Skip reload if data already exists and force_reload is False
    if not force_reload and collection.count() > 0:
        print(f"[RAG] Collection already has {collection.count()} chunks. Skipping reload.")
        return

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

        step = 120
        overlap = 40
        start = 0
        while start < len(text):
            end = start + step
            chunk = text[start:end].strip()
            if len(chunk) > 20:
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
        print("[RAG] WARNING: Collection is empty. Was load_policy_pdf() called?")
        return []

    n_results = min(n_results, count)
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )
    docs = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # Debug: print retrieved chunks and similarity scores
    print(f"\n[RAG DEBUG] Query: '{query}'")
    print(f"[RAG DEBUG] Retrieved {len(docs)} chunks:")
    for i, (doc, dist) in enumerate(zip(docs, distances)):
        score = round(1 - dist, 3)
        print(f"  [{i}] similarity={score} | {repr(doc)}")
    print()

    return docs