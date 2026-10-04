import os
import uuid
import json
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.ingest import extract_text, SUPPORTED_EXTENSIONS
from app.rag import chunk_text, add_to_store, retrieve, format_sources
from app import prompts
from app.llm import chat, get_llm_config


app = FastAPI(title="Deadline Guardian API", version="1.0.0")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-memory status job tracker per session_id
_UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}


# Pydantic Request Models
class AskRequest(BaseModel):
    session_id: str
    query: str


class CondenseRequest(BaseModel):
    session_id: str
    topic: Optional[str] = ""


class QuizRequest(BaseModel):
    session_id: str
    topic: Optional[str] = ""
    n: Optional[int] = Field(default=5, ge=1, le=10)


class TriageRequest(BaseModel):
    session_id: str
    hours_left: Optional[float] = Field(default=6.0, gt=0)


class TranscribedItem(BaseModel):
    text: str
    source: str
    page: Any


class ConfirmTextRequest(BaseModel):
    session_id: str
    items: List[TranscribedItem]


MAX_FILES = 10
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    _, _, model = get_llm_config()
    return {"model": model}


@app.get("/status/{session_id}")
def get_status(session_id: str):
    job = _UPLOAD_JOBS.get(session_id, {
        "status": "idle",
        "message": "No active processing job.",
        "skipped": []
    })
    return job


@app.post("/upload")
async def upload_files(
    session_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum allowed per upload is {MAX_FILES} files."
        )

    if not session_id or not session_id.strip():
        session_id = str(uuid.uuid4())

    _UPLOAD_JOBS[session_id] = {
        "status": "processing",
        "message": "Preparing files for processing...",
        "skipped": [],
        "transcriptions": []
    }

    def progress_callback(msg: str):
        if session_id in _UPLOAD_JOBS:
            _UPLOAD_JOBS[session_id]["message"] = msg
            if "Skipping" in msg:
                _UPLOAD_JOBS[session_id]["skipped"].append(msg)

    all_extracted: List[Dict[str, Any]] = []
    processed_count = 0

    with tempfile.TemporaryDirectory() as temp_dir:
        for file in files:
            filename = file.filename or "unknown"
            ext = Path(filename).suffix.lower()

            if ext not in SUPPORTED_EXTENSIONS:
                _UPLOAD_JOBS[session_id]["status"] = "error"
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type '{ext}' for file '{filename}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                )

            contents = await file.read()
            if len(contents) > MAX_FILE_SIZE:
                _UPLOAD_JOBS[session_id]["status"] = "error"
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{filename}' exceeds maximum size limit of 10MB."
                )

            temp_file_path = Path(temp_dir) / filename
            temp_file_path.write_bytes(contents)

            try:
                extracted = extract_text(temp_file_path, progress_callback=progress_callback)
                all_extracted.extend(extracted)
                processed_count += 1
            except Exception as e:
                _UPLOAD_JOBS[session_id]["status"] = "error"
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process '{filename}': {str(e)}"
                )

    if not all_extracted:
        _UPLOAD_JOBS[session_id]["status"] = "error"
        raise HTTPException(status_code=400, detail="No readable text found in uploaded files.")

    # Separate vision items (handwritten/diagram transcriptions needing review)
    vision_items = [item for item in all_extracted if item.get("is_vision")]
    text_items = [item for item in all_extracted if not item.get("is_vision")]

    # Immediately index standard text items
    text_chunks_count = 0
    if text_items:
        chunks = chunk_text(text_items, chunk_size=500, chunk_overlap=50)
        text_chunks_count = len(chunks)
        add_to_store(session_id, chunks)

    if vision_items:
        _UPLOAD_JOBS[session_id]["status"] = "needs_confirmation"
        _UPLOAD_JOBS[session_id]["message"] = "Transcriptions ready for your review."
        _UPLOAD_JOBS[session_id]["transcriptions"] = vision_items

        return {
            "session_id": session_id,
            "requires_confirmation": True,
            "transcriptions": vision_items,
            "text_chunks_created": text_chunks_count,
            "files_processed": processed_count,
            "skipped": _UPLOAD_JOBS[session_id]["skipped"]
        }

    # No vision items -> indexing complete
    total_chunks = add_to_store(session_id, [])
    _UPLOAD_JOBS[session_id]["status"] = "complete"
    _UPLOAD_JOBS[session_id]["message"] = "Ingestion complete."

    return {
        "session_id": session_id,
        "requires_confirmation": False,
        "files_processed": processed_count,
        "chunks_created": text_chunks_count,
        "total_chunks": total_chunks,
        "skipped": _UPLOAD_JOBS[session_id]["skipped"]
    }


@app.post("/confirm_text")
def confirm_transcription_text(req: ConfirmTextRequest):
    if not req.items:
        raise HTTPException(status_code=400, detail="No transcribed items provided for confirmation.")

    docs = [{"text": item.text, "source": item.source, "page": item.page} for item in req.items]
    chunks = chunk_text(docs, chunk_size=500, chunk_overlap=50)
    total_chunks = add_to_store(req.session_id, chunks)

    if req.session_id in _UPLOAD_JOBS:
        _UPLOAD_JOBS[req.session_id]["status"] = "complete"
        _UPLOAD_JOBS[req.session_id]["message"] = "Confirmed transcriptions indexed successfully."

    return {
        "session_id": req.session_id,
        "chunks_created": len(chunks),
        "total_chunks": total_chunks
    }


@app.post("/ask")
def ask_question(req: AskRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    chunks = retrieve(req.session_id, req.query, k=6)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    sys_prompt, user_prompt = prompts.build_ask_prompt(req.query, chunks)
    answer = chat(sys_prompt, user_prompt)
    sources = format_sources(chunks)

    return {"answer": answer, "sources": sources}


@app.post("/condense")
def condense_topic(req: CondenseRequest):
    search_topic = req.topic if req.topic and req.topic.strip() else "main concepts core definitions summary"
    chunks = retrieve(req.session_id, search_topic, k=8)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    sys_prompt, user_prompt = prompts.build_condense_prompt(req.topic or "", chunks)
    answer = chat(sys_prompt, user_prompt)
    sources = format_sources(chunks)

    return {"answer": answer, "sources": sources}


def parse_quiz_json(raw_response: str) -> Optional[List[Dict[str, Any]]]:
    """Helper to strip code blocks and parse quiz JSON."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return None


@app.post("/quiz")
def generate_quiz(req: QuizRequest):
    search_topic = req.topic if req.topic and req.topic.strip() else "key definitions multiple choice questions"
    chunks = retrieve(req.session_id, search_topic, k=8)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    sys_prompt, user_prompt = prompts.build_quiz_prompt(req.topic or "", chunks, n_questions=req.n)
    raw_answer = chat(sys_prompt, user_prompt)
    parsed_quiz = parse_quiz_json(raw_answer)

    # Retry once if initial JSON parse failed
    if parsed_quiz is None:
        retry_user_prompt = user_prompt + "\n\nIMPORTANT: Return STRICT RAW JSON ONLY. No markdown, no prose."
        raw_answer = chat(sys_prompt, retry_user_prompt)
        parsed_quiz = parse_quiz_json(raw_answer)

    if parsed_quiz is None:
        parsed_quiz = [{
            "question": "Could not format quiz as JSON.",
            "options": ["A) View raw answer"],
            "answer": "A",
            "explanation": raw_answer
        }]

    sources = format_sources(chunks)
    return {"quiz": parsed_quiz, "sources": sources}


@app.post("/triage")
def deadline_triage(req: TriageRequest):
    chunks = retrieve(req.session_id, "syllabus exam core topics overview important timetable", k=10)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    sys_prompt, user_prompt = prompts.build_triage_prompt(req.hours_left or 6.0, chunks)
    answer = chat(sys_prompt, user_prompt)
    sources = format_sources(chunks)

    return {"answer": answer, "sources": sources}


# Mount Static Files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def read_root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Deadline Guardian API is running."}
