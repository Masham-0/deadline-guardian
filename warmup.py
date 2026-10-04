import os
from pathlib import Path

# Set cache dir to project-local .cache/fastembed
cache_dir = str(Path(__file__).parent / ".cache" / "fastembed")
os.environ["FASTEMBED_CACHE_DIR"] = cache_dir

try:
    from fastembed import TextEmbedding
    print(f"Pre-warming embedding model BAAI/bge-small-en-v1.5 into {cache_dir}...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=cache_dir)
    # Perform a dummy embedding call to complete model initialization
    list(model.embed(["Pre-warming fastembed model cache."]))
    print("Embedding model cache successfully pre-warmed!")
except Exception as e:
    print(f"[Warning] Fastembed warm-up script error: {e}")
