import os
import re
import time
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

# Ensure Hugging Face token is active in environment if present
hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
if hf_token:
    os.environ["HF_TOKEN"] = hf_token
    os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token

# Ensure fastembed cache directory is set to project-local .cache/fastembed if not provided
if "FASTEMBED_CACHE_DIR" not in os.environ:
    os.environ["FASTEMBED_CACHE_DIR"] = str(Path(__file__).parent.parent / ".cache" / "fastembed")

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

_EMBED_MODEL: Optional[Any] = None

# In-memory vector store per session_id
# Structure: { session_id: { "chunks": List[Dict], "embeddings": np.ndarray, "last_accessed": float } }
_STORES: Dict[str, Dict[str, Any]] = {}

MAX_CHUNKS_PER_SESSION = 1000
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
SESSION_TTL_SECONDS = 7200  # 2 hours


def get_embedding_model() -> Any:
    """Lazy-load fastembed BAAI/bge-small-en-v1.5 embedding model."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        if TextEmbedding is None:
            raise ImportError("fastembed is required. Run `pip install fastembed`.")
        cache_dir = os.environ.get("FASTEMBED_CACHE_DIR")
        print(f"Loading embedding model ({EMBEDDING_MODEL_NAME}) from cache_dir={cache_dir}...")
        _EMBED_MODEL = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=cache_dir)
    return _EMBED_MODEL


def chunk_text(
    docs: List[Dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Split extracted documents into chunks (~500 words with ~50 words overlap).
    Preserves source and page metadata.
    """
    chunks: List[Dict[str, Any]] = []

    for doc in docs:
        text = doc.get("text", "").strip()
        source = doc.get("source", "unknown")
        page = doc.get("page", 1)

        words = text.split()
        if not words:
            continue

        if len(words) <= chunk_size:
            chunks.append({
                "text": text,
                "source": source,
                "page": page
            })
            continue

        start = 0
        step = chunk_size - chunk_overlap
        if step <= 0:
            step = chunk_size

        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]
            chunk_str = " ".join(chunk_words)

            chunks.append({
                "text": chunk_str,
                "source": source,
                "page": page
            })

            start += step

    return chunks


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2 normalize vectors for cosine similarity computation."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    return vectors / norms


def embed_texts(texts: List[str]) -> np.ndarray:
    """Generate vector embeddings for a list of text strings."""
    model = get_embedding_model()
    embeddings_list = list(model.embed(texts))
    matrix = np.array(embeddings_list, dtype=np.float32)
    return _normalize(matrix)


def cleanup_expired_sessions(ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
    """Remove sessions that have not been accessed within ttl_seconds."""
    now = time.time()
    expired = [
        sid for sid, data in _STORES.items()
        if now - data.get("last_accessed", now) > ttl_seconds
    ]
    for sid in expired:
        del _STORES[sid]


def add_to_store(session_id: str, chunks: List[Dict[str, Any]]) -> int:
    """
    Embed and store chunks in-memory for session_id.
    Caps chunks per session at MAX_CHUNKS_PER_SESSION.
    """
    cleanup_expired_sessions()

    if not chunks:
        return len(_STORES.get(session_id, {}).get("chunks", []))

    if session_id not in _STORES:
        _STORES[session_id] = {
            "chunks": [],
            "embeddings": np.empty((0, 384), dtype=np.float32),
            "last_accessed": time.time()
        }

    _STORES[session_id]["last_accessed"] = time.time()
    existing_chunks = _STORES[session_id]["chunks"]
    existing_embeddings = _STORES[session_id]["embeddings"]

    available_space = MAX_CHUNKS_PER_SESSION - len(existing_chunks)
    if available_space <= 0:
        print(f"[Warning] Session '{session_id}' reached maximum capacity ({MAX_CHUNKS_PER_SESSION} chunks).")
        return len(existing_chunks)

    chunks_to_add = chunks[:available_space]
    texts = [c["text"] for c in chunks_to_add]

    new_embeddings = embed_texts(texts)

    _STORES[session_id]["chunks"] = existing_chunks + chunks_to_add
    if existing_embeddings.size == 0:
        _STORES[session_id]["embeddings"] = new_embeddings
    else:
        _STORES[session_id]["embeddings"] = np.vstack([existing_embeddings, new_embeddings])

    return len(_STORES[session_id]["chunks"])


def retrieve(session_id: str, query: str, k: int = 6) -> List[Dict[str, Any]]:
    """
    Retrieve top k relevant chunks for query in session_id using cosine similarity.
    """
    cleanup_expired_sessions()

    if session_id not in _STORES or not _STORES[session_id]["chunks"]:
        return []

    store = _STORES[session_id]
    store["last_accessed"] = time.time()
    chunks = store["chunks"]
    embeddings = store["embeddings"]

    query_vec = embed_texts([query])
    scores = np.dot(embeddings, query_vec.T).squeeze(axis=1)

    top_k_indices = np.argsort(scores)[::-1][:min(k, len(scores))]

    results = []
    for idx in top_k_indices:
        item = dict(chunks[idx])
        item["score"] = float(scores[idx])
        results.append(item)

    return results


def retrieve_multi_topic(
    session_id: str,
    query: str,
    k_per_topic: int = 5,
    max_total_chunks: int = 14
) -> List[Dict[str, Any]]:
    """
    Decomposes multi-line or multi-topic queries, performs vector retrieval for each sub-topic,
    and merges/deduplicates top chunks so that EVERY sub-topic gets sufficient context.
    """
    cleanup_expired_sessions()

    if session_id not in _STORES or not _STORES[session_id]["chunks"]:
        return []

    # Decompose query into sub-topics by line breaks, question marks, or bullet points
    raw_sub_queries = [line.strip() for line in re.split(r'[\n;?]+', query) if line.strip()]
    
    # Filter out extremely short connector words
    sub_queries = [q for q in raw_sub_queries if len(q) >= 3]
    
    if not sub_queries:
        sub_queries = [query.strip()]

    # Also include the overall query as a baseline
    if len(sub_queries) > 1 and query.strip() not in sub_queries:
        sub_queries.append(query.strip())

    seen_keys = set()
    combined_chunks = []

    for sq in sub_queries:
        top_chunks = retrieve(session_id, sq, k=k_per_topic)
        for c in top_chunks:
            # Deduplicate by (source, page, snippet hash)
            key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
            if key not in seen_keys:
                seen_keys.add(key)
                combined_chunks.append(c)

    # Sort combined chunks by similarity score descending
    combined_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)

    return combined_chunks[:max_total_chunks]


def format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format retrieved chunks into clean JSON source objects."""
    sources = []
    seen = set()
    for c in chunks:
        key = (c.get("source"), c.get("page"))
        if key in seen:
            continue
        seen.add(key)
        snippet = c.get("text", "")
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        sources.append({
            "file": c.get("source", "unknown"),
            "page": c.get("page", 1),
            "snippet": snippet
        })
    return sources


def save_store(filepath: str | Path = ".store.pkl") -> None:
    """Save in-memory stores to disk."""
    path = Path(filepath)
    with open(path, "wb") as f:
        pickle.dump(_STORES, f)


def load_store(filepath: str | Path = ".store.pkl") -> bool:
    """Load session stores from disk if file exists."""
    global _STORES
    path = Path(filepath)
    if not path.exists():
        return False
    try:
        with open(path, "rb") as f:
            loaded = pickle.load(f)
            if isinstance(loaded, dict):
                _STORES = loaded
                return True
    except Exception as e:
        print(f"[Warning] Could not load vector store from {path}: {e}")
    return False
