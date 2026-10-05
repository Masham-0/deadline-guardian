import os
import re
import uuid
import json
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.ingest import extract_text, SUPPORTED_EXTENSIONS
from app.rag import chunk_text, add_to_store, clear_store, retrieve, retrieve_multi_topic, retrieve_triage_context, format_sources
from app import prompts
from app.llm import chat, chat_stream, get_llm_config


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


def process_upload_in_background(session_id: str, file_records: List[Dict[str, Any]], temp_dir_path: str):
    """Background task to extract, chunk, and index files without blocking HTTP requests."""
    try:
        def progress_callback(msg: str):
            if session_id in _UPLOAD_JOBS:
                _UPLOAD_JOBS[session_id]["message"] = msg
                if "Skipping" in msg:
                    _UPLOAD_JOBS[session_id]["skipped"].append(msg)

        all_extracted: List[Dict[str, Any]] = []
        processed_count = 0

        for record in file_records:
            filename = record["filename"]
            file_path = Path(record["path"])
            try:
                progress_callback(f"Reading '{filename}'...")
                extracted = extract_text(file_path, progress_callback=progress_callback)
                all_extracted.extend(extracted)
                processed_count += 1
            except Exception as e:
                print(f"[Warning] Failed extraction on '{filename}': {e}")
                if session_id in _UPLOAD_JOBS:
                    _UPLOAD_JOBS[session_id]["skipped"].append(f"Failed '{filename}': {e}")

        if not all_extracted:
            if session_id in _UPLOAD_JOBS:
                _UPLOAD_JOBS[session_id]["status"] = "error"
                _UPLOAD_JOBS[session_id]["message"] = "No readable text found in uploaded files."
            return

        vision_items = [item for item in all_extracted if item.get("is_vision")]
        text_items = [item for item in all_extracted if not item.get("is_vision")]

        text_chunks_count = 0
        if text_items:
            progress_callback(f"Chunking {len(text_items)} text segments...")
            chunks = chunk_text(text_items, chunk_size=150, chunk_overlap=30)
            text_chunks_count = len(chunks)
            progress_callback(f"Indexing {text_chunks_count} chunks into vector store...")
            add_to_store(session_id, chunks)

        total_chunks = add_to_store(session_id, [])

        if vision_items:
            _UPLOAD_JOBS[session_id]["status"] = "needs_confirmation"
            _UPLOAD_JOBS[session_id]["message"] = "Transcriptions ready for your review."
            _UPLOAD_JOBS[session_id]["transcriptions"] = vision_items
            _UPLOAD_JOBS[session_id]["chunks_created"] = text_chunks_count
            _UPLOAD_JOBS[session_id]["files_processed"] = processed_count
            _UPLOAD_JOBS[session_id]["total_chunks"] = total_chunks
        else:
            _UPLOAD_JOBS[session_id]["status"] = "complete"
            _UPLOAD_JOBS[session_id]["message"] = "Ingestion complete."
            _UPLOAD_JOBS[session_id]["chunks_created"] = text_chunks_count
            _UPLOAD_JOBS[session_id]["files_processed"] = processed_count
            _UPLOAD_JOBS[session_id]["total_chunks"] = total_chunks

    except Exception as e:
        if session_id in _UPLOAD_JOBS:
            _UPLOAD_JOBS[session_id]["status"] = "error"
            _UPLOAD_JOBS[session_id]["message"] = f"Ingestion error: {str(e)}"
    finally:
        try:
            shutil.rmtree(temp_dir_path, ignore_errors=True)
        except Exception:
            pass


@app.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...)
):
    try:
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
            "message": "Validating uploaded files...",
            "skipped": [],
            "transcriptions": [],
            "files_processed": 0,
            "chunks_created": 0,
            "total_chunks": 0
        }

        temp_dir = tempfile.mkdtemp()
        file_records = []

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
            file_records.append({"filename": filename, "path": str(temp_file_path)})

        background_tasks.add_task(process_upload_in_background, session_id, file_records, temp_dir)

        return {
            "session_id": session_id,
            "status": "processing",
            "message": "Files received. Processing background ingestion..."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@app.post("/confirm_text")
def confirm_transcription_text(req: ConfirmTextRequest):
    if not req.items:
        raise HTTPException(status_code=400, detail="No transcribed items provided for confirmation.")

    docs = [{"text": item.text, "source": item.source, "page": item.page} for item in req.items]
    chunks = chunk_text(docs, chunk_size=150, chunk_overlap=30)
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

    raw_sub_queries = [line.strip() for line in re.split(r'[\n;?]+', req.query) if line.strip()]
    sub_queries = [q for q in raw_sub_queries if len(q) >= 3]
    if not sub_queries:
        sub_queries = [req.query.strip()]

    answers = []
    all_chunks = []
    seen_keys = set()

    # Process EACH sub-topic with its own focused vector search and dedicated AI call
    for topic_query in sub_queries:
        chunks = retrieve_multi_topic(req.session_id, topic_query, k_per_topic=7, max_total_chunks=14)
        if not chunks:
            # Fallback to general vector search if focused search yields no hits
            chunks = retrieve(req.session_id, topic_query, k=7)
        if not chunks:
            continue

        for c in chunks:
            key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
            if key not in seen_keys:
                seen_keys.add(key)
                all_chunks.append(c)

        sys_prompt, user_prompt = prompts.build_ask_prompt(topic_query, chunks)
        topic_answer = chat(sys_prompt, user_prompt)
        answers.append(topic_answer)

    if not answers:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    final_answer = "\n\n---\n\n".join(answers)
    sources = format_sources(all_chunks)

    return {"answer": final_answer, "sources": sources}


@app.post("/ask/stream")
def ask_question_stream(req: AskRequest):
    from fastapi.responses import StreamingResponse

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    raw_sub_queries = [line.strip() for line in re.split(r'[\n;?]+', req.query) if line.strip()]
    sub_queries = [q for q in raw_sub_queries if len(q) >= 3]
    if not sub_queries:
        sub_queries = [req.query.strip()]

    all_chunks = []
    seen_keys = set()

    def generate_events():
        for i, topic_query in enumerate(sub_queries):
            chunks = retrieve_multi_topic(req.session_id, topic_query, k_per_topic=7, max_total_chunks=14)
            if not chunks:
                chunks = retrieve(req.session_id, topic_query, k=7)

            for c in chunks:
                key = (c.get("source"), c.get("page"), hash(c.get("text", "")[:100]))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_chunks.append(c)

            if i > 0:
                yield f"data: {json.dumps({'type': 'chunk', 'text': '\n\n---\n\n'})}\n\n"

            sys_prompt, user_prompt = prompts.build_ask_prompt(topic_query, chunks)
            for token in chat_stream(sys_prompt, user_prompt):
                yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"

        sources = format_sources(all_chunks)
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_events(), media_type="text/event-stream")


@app.post("/triage")
def deadline_triage(req: TriageRequest):
    triage_data = retrieve_triage_context(req.session_id, max_total_chunks=38)

    if not triage_data.get("all_chunks"):
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    # Pass 1: High-Level Priority Matrix & Hour-by-Hour Timetable
    sys1, user1 = prompts.build_triage_pass1_prompt(req.hours_left or 6.0, triage_data)
    pass1_answer = chat(sys1, user1)

    # Extract high-priority topic titles from Pass 1 output (or fallback to top syllabus topics)
    extracted_topics = []
    for line in pass1_answer.splitlines():
        if "Tier 1" in line or "🔴" in line or "Must Know" in line:
            clean_line = re.sub(r'[*`#🔴🟡🟢]', '', line).strip()
            if ":" in clean_line:
                clean_line = clean_line.split(":", 1)[1].strip()
            extracted_topics.extend([t.strip() for t in clean_line.split(",") if len(t.strip()) > 3])

    if not extracted_topics:
        extracted_topics = ["Core Exam Concepts", "High Weightage Formulas & Definitions"]

    # Limit to top 5 topics max for Pass 2 deep-dive
    top_topics = extracted_topics[:5]

    # Perform focused vector retrieval for the extracted topic batch
    topic_query = " ".join(top_topics)
    pass2_chunks = retrieve_multi_topic(req.session_id, topic_query, k_per_topic=7, max_total_chunks=20)
    if not pass2_chunks:
        pass2_chunks = triage_data.get("all_chunks", [])[:15]

    # Pass 2: Deep-Dive Revision Cheats & Notes for high-yield topics
    sys2, user2 = prompts.build_triage_pass2_prompt(req.hours_left or 6.0, top_topics, pass2_chunks)
    pass2_answer = chat(sys2, user2)

    # Combine Pass 1 + Pass 2
    full_answer = f"{pass1_answer}\n\n---\n\n{pass2_answer}"

    # Merge sources
    combined_chunks = triage_data.get("all_chunks", []) + pass2_chunks
    sources = format_sources(combined_chunks)

    return {"answer": full_answer, "sources": sources}


@app.post("/triage/stream")
def deadline_triage_stream(req: TriageRequest):
    from fastapi.responses import StreamingResponse

    triage_data = retrieve_triage_context(req.session_id, max_total_chunks=38)

    if not triage_data.get("all_chunks"):
        raise HTTPException(
            status_code=404,
            detail=f"No context found for session '{req.session_id}'. Please upload study materials first."
        )

    def generate_triage_stream():
        # Pass 1
        sys1, user1 = prompts.build_triage_pass1_prompt(req.hours_left or 6.0, triage_data)
        pass1_full = []
        for token in chat_stream(sys1, user1):
            pass1_full.append(token)
            yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"

        pass1_text = "".join(pass1_full)
        yield f"data: {json.dumps({'type': 'chunk', 'text': '\n\n---\n\n'})}\n\n"

        # Pass 2
        extracted_topics = []
        for line in pass1_text.splitlines():
            if "Tier 1" in line or "🔴" in line or "Must Know" in line:
                clean_line = re.sub(r'[*`#🔴🟡🟢]', '', line).strip()
                if ":" in clean_line:
                    clean_line = clean_line.split(":", 1)[1].strip()
                extracted_topics.extend([t.strip() for t in clean_line.split(",") if len(t.strip()) > 3])

        if not extracted_topics:
            extracted_topics = ["Core Exam Concepts", "High Weightage Formulas & Definitions"]

        top_topics = extracted_topics[:5]
        topic_query = " ".join(top_topics)
        pass2_chunks = retrieve_multi_topic(req.session_id, topic_query, k_per_topic=7, max_total_chunks=20)
        if not pass2_chunks:
            pass2_chunks = triage_data.get("all_chunks", [])[:15]

        sys2, user2 = prompts.build_triage_pass2_prompt(req.hours_left or 6.0, top_topics, pass2_chunks)
        for token in chat_stream(sys2, user2):
            yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"

        combined_chunks = triage_data.get("all_chunks", []) + pass2_chunks
        sources = format_sources(combined_chunks)
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_triage_stream(), media_type="text/event-stream")


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
