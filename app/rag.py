import os
import re
import time
import uuid
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

# Limit thread concurrency in ONNX/FastEmbed to prevent starving Uvicorn event loop on single/dual core hosting (Render)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# Ensure fastembed cache directory is set to project-local .cache/fastembed if not provided
if "FASTEMBED_CACHE_DIR" not in os.environ:
    os.environ["FASTEMBED_CACHE_DIR"] = str(Path(__file__).parent.parent / ".cache" / "fastembed")

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue
except ImportError:
    QdrantClient = None

_EMBED_MODEL: Optional[Any] = None
_QDRANT_CLIENT: Optional[Any] = None
_QDRANT_INIT_ATTEMPTED: bool = False
QDRANT_COLLECTION = "deadline_guardian_chunks"

# In-memory vector store fallback per session_id
# Structure: { session_id: { "chunks": List[Dict], "embeddings": np.ndarray, "last_accessed": float } }
_STORES: Dict[str, Dict[str, Any]] = {}

MAX_CHUNKS_PER_SESSION = 1000
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
SESSION_TTL_SECONDS = 7200  # 2 hours


def get_qdrant_client() -> Optional[Any]:
    """Initialize connection to Qdrant Cloud cluster if QDRANT_URL environment variable is provided."""
    global _QDRANT_CLIENT, _QDRANT_INIT_ATTEMPTED
    if _QDRANT_INIT_ATTEMPTED:
        return _QDRANT_CLIENT

    _QDRANT_INIT_ATTEMPTED = True
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()

    if not qdrant_url or QdrantClient is None:
        print("[Qdrant] QDRANT_URL not set or qdrant-client not installed. Using in-memory store.")
        return None

    try:
        print(f"[Qdrant] Connecting to Qdrant Cloud at {qdrant_url}...")
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key if qdrant_api_key else None, timeout=10.0)
        
        collections = [c.name for c in client.get_collections().collections]
        if QDRANT_COLLECTION not in collections:
            print(f"[Qdrant] Creating collection '{QDRANT_COLLECTION}'...")
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )
        _QDRANT_CLIENT = client
        print("[Qdrant] Successfully connected and initialized Qdrant Cloud collection!")
    except Exception as e:
        print(f"[Warning] Could not connect to Qdrant Cloud: {e}. Falling back to in-memory store.")
        _QDRANT_CLIENT = None

    return _QDRANT_CLIENT


def get_embedding_model() -> Any:
    """Lazy-load fastembed BAAI/bge-small-en-v1.5 embedding model with single-thread CPU execution."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        if TextEmbedding is None:
            raise ImportError("fastembed is required. Run `pip install fastembed`.")
        cache_dir = os.environ.get("FASTEMBED_CACHE_DIR")
        print(f"Loading embedding model ({EMBEDDING_MODEL_NAME}) from cache_dir={cache_dir}...")
        try:
            _EMBED_MODEL = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=cache_dir, threads=1)
        except TypeError:
            _EMBED_MODEL = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=cache_dir)
    return _EMBED_MODEL


def chunk_text(
    docs: List[Dict[str, Any]],
    chunk_size: int = 150,
    chunk_overlap: int = 30
) -> List[Dict[str, Any]]:
    """
    Split extracted documents into fine-grained paragraph-aware chunks (~150 words with ~30 words overlap).
    Preserves source and page metadata.
    """
    chunks: List[Dict[str, Any]] = []

    for doc in docs:
        text = doc.get("text", "").strip()
        source = doc.get("source", "unknown")
        page = doc.get("page", 1)

        if not text:
            continue

        # First split by paragraph boundaries
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

        current_words: List[str] = []

        for paragraph in paragraphs:
            p_words = paragraph.split()
            if not p_words:
                continue

            # If single paragraph is small, accumulate it
            if len(current_words) + len(p_words) <= chunk_size:
                current_words.extend(p_words)
            else:
                # Flush current accumulated chunk if any
                if current_words:
                    chunks.append({
                        "text": " ".join(current_words),
                        "source": source,
                        "page": page
                    })
                    current_words = []

                # If paragraph itself is larger than chunk_size, apply sliding window
                if len(p_words) > chunk_size:
                    start = 0
                    step = chunk_size - chunk_overlap
                    if step <= 0:
                        step = chunk_size
                    while start < len(p_words):
                        end = start + chunk_size
                        chunk_words = p_words[start:end]
                        chunks.append({
                            "text": " ".join(chunk_words),
                            "source": source,
                            "page": page
                        })
                        start += step
                else:
                    current_words = list(p_words)

        if current_words:
            chunks.append({
                "text": " ".join(current_words),
                "source": source,
                "page": page
            })

    return chunks


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2 normalize vectors for cosine similarity computation."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    return vectors / norms


def embed_texts(texts: List[str], batch_size: int = 8) -> np.ndarray:
    """Generate vector embeddings for a list of text strings in small micro-batches to preserve CPU & memory."""
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    model = get_embedding_model()
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeds = list(model.embed(batch, batch_size=batch_size))
        all_embeddings.extend(batch_embeds)
        time.sleep(0.12)  # 120ms yield to give Uvicorn event loop ample CPU time for HTTP status polling
    matrix = np.array(all_embeddings, dtype=np.float32)
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


def clear_store(session_id: str) -> None:
    """Clear all stored chunks and embeddings for session_id from Qdrant Cloud and local store."""
    if session_id in _STORES:
        del _STORES[session_id]

    qdrant = get_qdrant_client()
    if qdrant:
        try:
            qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
                )
            )
            print(f"[Qdrant] Successfully deleted all vectors for session '{session_id}' from Qdrant Cloud.")
        except Exception as e:
            print(f"[Warning] Failed to delete session '{session_id}' vectors from Qdrant: {e}")


def add_to_store(
    session_id: str,
    chunks: List[Dict[str, Any]],
    progress_callback: Optional[Any] = None
) -> int:
    """
    Embed and store chunks for session_id in Qdrant Cloud (if configured) and local in-memory store.
    Caps chunks per session at MAX_CHUNKS_PER_SESSION.
    """
    cleanup_expired_sessions()
    qdrant = get_qdrant_client()

    if not chunks:
        if qdrant:
            try:
                res = qdrant.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]),
                    limit=1000,
                    with_payload=False,
                    with_vectors=False
                )
                return len(res[0])
            except Exception:
                pass
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
    total_to_add = len(chunks_to_add)

    # Process embedding in micro-batches of 8 for CPU & memory efficiency
    batch_size = 8
    new_embeddings_list = []

    for i in range(0, total_to_add, batch_size):
        batch_chunks = chunks_to_add[i:i + batch_size]
        batch_texts = [c["text"] for c in batch_chunks]
        if progress_callback:
            progress_callback(f"Indexing chunks ({min(i + batch_size, total_to_add)}/{total_to_add})...")
        
        b_embeds = embed_texts(batch_texts, batch_size=8)
        new_embeddings_list.append(b_embeds)

        if qdrant:
            points = []
            for c, vec in zip(batch_chunks, b_embeds):
                point_id = str(uuid.uuid4())
                points.append(PointStruct(
                    id=point_id,
                    vector=vec.tolist(),
                    payload={
                        "session_id": session_id,
                        "text": c.get("text", ""),
                        "source": c.get("source", "unknown"),
                        "page": c.get("page", 1)
                    }
                ))
            try:
                qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
            except Exception as e:
                print(f"[Warning] Failed to upsert points into Qdrant Cloud: {e}")

    if new_embeddings_list:
        new_embeddings = np.vstack(new_embeddings_list)
        _STORES[session_id]["chunks"] = existing_chunks + chunks_to_add
        if existing_embeddings.size == 0:
            _STORES[session_id]["embeddings"] = new_embeddings
        else:
            _STORES[session_id]["embeddings"] = np.vstack([existing_embeddings, new_embeddings])

    return len(_STORES[session_id]["chunks"])


def retrieve(session_id: str, query: str, k: int = 6, min_score: float = 0.35) -> List[Dict[str, Any]]:
    """
    Retrieve top k relevant chunks for query in session_id using Qdrant Cloud vector search or cosine similarity fallback.
    Filters out chunks with similarity score below min_score to avoid out-of-context citations.
    """
    cleanup_expired_sessions()
    qdrant = get_qdrant_client()

    if qdrant:
        try:
            query_matrix = embed_texts([query])
            if query_matrix.size > 0:
                query_vec = query_matrix[0].tolist()
                hits = qdrant.search(
                    collection_name=QDRANT_COLLECTION,
                    query_vector=query_vec,
                    query_filter=Filter(
                        must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
                    ),
                    limit=k,
                    score_threshold=min_score
                )
                if hits:
                    results = []
                    for hit in hits:
                        payload = hit.payload or {}
                        results.append({
                            "text": payload.get("text", ""),
                            "source": payload.get("source", "unknown"),
                            "page": payload.get("page", 1),
                            "score": float(hit.score)
                        })
                    return results
        except Exception as e:
            print(f"[Warning] Qdrant search error: {e}. Falling back to in-memory store.")

    # Fallback to local in-memory store
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
        score_val = float(scores[idx])
        # Filter out irrelevant chunks below similarity threshold unless no chunks pass
        if score_val >= min_score or len(results) == 0 and score_val >= 0.20:
            item = dict(chunks[idx])
            item["score"] = score_val
            results.append(item)

    return results


def retrieve_multi_topic(
    session_id: str,
    query: str,
    k_per_topic: int = 7,
    max_total_chunks: int = 24
) -> List[Dict[str, Any]]:
    """
    Decomposes multi-line or multi-topic queries, performs vector retrieval for each sub-topic,
    and merges/deduplicates top chunks so that EVERY sub-topic gets sufficient context.
    """
    cleanup_expired_sessions()

    if session_id not in _STORES or not _STORES[session_id]["chunks"]:
        return []

    raw_sub_queries = [line.strip() for line in re.split(r'[\n;?]+', query) if line.strip()]
    sub_queries = [q for q in raw_sub_queries if len(q) >= 3]

    if not sub_queries:
        sub_queries = [query.strip()]

    if len(sub_queries) > 1 and query.strip() not in sub_queries:
        sub_queries.append(query.strip())

    seen_keys = set()
    combined_chunks = []

    for sq in sub_queries:
        top_chunks = retrieve(session_id, sq, k=k_per_topic)
        for c in top_chunks:
            key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
            if key not in seen_keys:
                seen_keys.add(key)
                combined_chunks.append(c)

    combined_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
    return combined_chunks[:max_total_chunks]


def retrieve_triage_context(
    session_id: str,
    max_total_chunks: int = 38
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Multi-pass triage retrieval:
    1. Detects & extracts syllabus / PYQ chunks (files containing syllabus, pyq, exam, question, paper, pattern).
    2. Sweeps across all uploaded slide decks/files to construct a full 100% course overview map.
    """
    cleanup_expired_sessions()

    if session_id not in _STORES or not _STORES[session_id]["chunks"]:
        return {"syllabus_chunks": [], "course_chunks": [], "all_chunks": []}

    store = _STORES[session_id]
    all_chunks = store["chunks"]

    syllabus_keywords = ("syllabus", "pyq", "exam", "question", "paper", "pattern", "test", "midterm", "final")

    syllabus_chunks = []
    course_chunks_by_file: Dict[str, List[Dict[str, Any]]] = {}

    for c in all_chunks:
        source_lower = c.get("source", "").lower()
        if any(kw in source_lower for kw in syllabus_keywords):
            syllabus_chunks.append(c)
        else:
            filename = c.get("source", "unknown")
            if filename not in course_chunks_by_file:
                course_chunks_by_file[filename] = []
            course_chunks_by_file[filename].append(c)

    # Perform vector search over syllabus topics if syllabus chunks are few
    if not syllabus_chunks:
        syllabus_chunks = retrieve(session_id, "syllabus exam questions core topics marks weightage", k=10)

    # Broad sweep across all files: pick representative chunks evenly from each file
    selected_course_chunks = []
    seen_keys = set()

    # First add syllabus chunks
    for c in syllabus_chunks[:12]:
        key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
        seen_keys.add(key)

    # Interleave chunks from each file evenly
    if course_chunks_by_file:
        max_per_file = max(1, (max_total_chunks - len(seen_keys)) // len(course_chunks_by_file) + 1)
        for fname, fchunks in course_chunks_by_file.items():
            for c in fchunks[:max_per_file]:
                key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
                if key not in seen_keys:
                    seen_keys.add(key)
                    selected_course_chunks.append(c)
                if len(selected_course_chunks) + len(syllabus_chunks) >= max_total_chunks:
                    break
            if len(selected_course_chunks) + len(syllabus_chunks) >= max_total_chunks:
                break

    # If space remains, add vector overview chunks
    if len(selected_course_chunks) + len(syllabus_chunks) < max_total_chunks:
        extra_overview = retrieve(session_id, "overview chapters core concepts study plan", k=12)
        for c in extra_overview:
            key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
            if key not in seen_keys:
                seen_keys.add(key)
                selected_course_chunks.append(c)
            if len(selected_course_chunks) + len(syllabus_chunks) >= max_total_chunks:
                break

    all_selected = (syllabus_chunks[:12] + selected_course_chunks)[:max_total_chunks]

    return {
        "syllabus_chunks": syllabus_chunks[:12],
        "course_chunks": selected_course_chunks,
        "all_chunks": all_selected
    }


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
