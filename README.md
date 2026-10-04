# Deadline Guardian 🎓⚡

> **Last-minute exam-prep study buddy.**  
> Built for the **DEV Hacktoberfest "Build for a Friend" Challenge**.  
> Upload your notes (PDF, PPTX, TXT, MD, JPG, PNG, WEBP); we chunk & embed them (RAG using `fastembed`); retrieved context + queries go to an open-weights LLM (Gemma via Google AI Studio or Ollama). Features vision transcription for handwritten notes and diagrams, interactive quiz flashcards, cheat sheets, and deadline panic timetables!

---

## ✨ Features

- 📁 **Multi-Format Ingestion**: Upload PDFs (scanned & digital), PowerPoint decks (`.pptx`), text notes (`.txt`, `.md`), and photos of handwritten notes (`.jpg`, `.png`, `.webp`).
- 👁️ **Vision & OCR**: Auto-detects scanned PDF pages and photos of handwritten notes using vision models. Provides an editable preview box before indexing.
- 🔍 **Local FastEmbed RAG**: High-speed, in-memory vector retrieval using `BAAI/bge-small-en-v1.5` cosine similarity embeddings.
- ❓ **Grounded Answers with Citations**: Answers questions strictly using uploaded notes with inline file & page citations (`[notes.pdf p.3]`).
- 📝 **High-Yield Cheat Sheets**: Condenses complex course topics into quick revision bullet points.
- 🎯 **Interactive Quiz Flashcards**: Generates multiple-choice quiz questions with instant option selection, visual answer feedback, and explanations.
- ⏱️ **Deadline Panic Timetable**: Generates a prioritized study schedule based on hours left before the exam.
- 🚀 **Render Free-Tier Ready**: Memory-optimized (< 350MB RAM footprint) with build-time model cache warming (`warmup.py`) and cold-start UX banners.

---

## 🚀 Local Setup & Execution

### 1. Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### 2. Installation
```bash
git clone https://github.com/your-username/deadline-guardian.git
cd deadline-guardian

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

#### Option A: Google AI Studio (Recommended for Vision & Gemma)
```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_google_ai_studio_api_key
LLM_MODEL=gemma-2-9b-it
```

#### Option B: Local Ollama
Ensure [Ollama](https://ollama.com) is running locally (`ollama run gemma:2b` or `ollama run llava` for vision):
```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma:2b
```

### 4. Running the Web Application
Start the FastAPI server:
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### 5. Using the CLI
You can also interact directly via the terminal:
```bash
# Ingest notes
python cli.py ingest blocks/

# Ask a question
python cli.py ask "What is Block 1 goal?"

# Generate cheat sheet
python cli.py condense "RAG Core"

# Generate quiz
python cli.py quiz "RAG" --n 5

# Generate panic schedule
python cli.py triage --hours 6
```

---

## 🌐 Deploying to Render Free Tier

`deadline-guardian` includes a production-ready [`render.yaml`](file:///home/mash/Projects/deadline-guardian/render.yaml) manifest designed for Render's free tier (512MB RAM).

### Deployment Steps:
1. Push your repository to GitHub.
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository. Render will automatically detect `render.yaml`.
5. Under Environment Variables in the Render dashboard, set:
   - `LLM_API_KEY`: Your production API key.
   - `LLM_BASE_URL`: `https://generativelanguage.googleapis.com/v1beta/openai/`
   - `LLM_MODEL`: `gemma-2-9b-it`
6. Click **Apply**.

Render will run `pip install -r requirements.txt && python warmup.py` to pre-cache the embedding model during build time, ensuring fast runtime response.

---

## 🛠️ Project Architecture

```
deadline-guardian/
├── app/
│   ├── ingest.py     # PDF, PPTX, TXT, MD & Vision Image extraction
│   ├── llm.py        # OpenAI-compatible API client & describe_image vision
│   ├── prompts.py    # Grounded prompts for Ask, Condense, Quiz, Triage
│   └── rag.py        # FastEmbed model, vector store & session TTL cleanup
├── static/
│   ├── index.html    # Mobile-friendly UI with drag-and-drop & tabs
│   ├── style.css     # Glassmorphic dark design system
│   └── app.js        # Session state, progress polling & interactive quiz engine
├── blocks/           # Project roadmap specifications
├── docs/
│   └── notes.txt     # User testing feedback & deployment logs
├── cli.py            # CLI entry point
├── main.py           # FastAPI web server & endpoints
├── render.yaml       # Render deployment manifest
├── warmup.py         # Build-time embedding cache warm-up script
└── requirements.txt  # Pinned Python dependencies
```

---

## 📄 License
MIT License. Built for the DEV Hacktoberfest "Build for a Friend" challenge.
