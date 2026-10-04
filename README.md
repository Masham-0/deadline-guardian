# Deadline Guardian 🎓

> **Last-minute exam-prep study buddy.**  
> Upload your notes (PDF, PPTX, TXT, MD); we chunk & embed them (RAG using `fastembed`); retrieved context + queries go to an open-weights LLM (Gemma via Google AI Studio or Ollama). Built for the DEV Hacktoberfest "Build for a Friend" challenge.

---

## 🚀 Quickstart & Setup

### 1. Installation
Clone the repository and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and set your API details:

```bash
cp .env.example .env
```

Default settings for Google AI Studio (OpenAI-compatible endpoint):
```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_google_ai_studio_key
LLM_MODEL=gemma-2-9b-it
```

For local Ollama:
```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma:2b
```

---

## 💻 CLI Usage

### 📥 1. Ingest Study Materials
Parse and index all notes from a folder or file:
```bash
python cli.py ingest blocks/
# Or ingest a specific folder/file:
python cli.py ingest samples/
```

### ❓ 2. Ask Questions (with Citations)
Ask questions grounded strictly in your ingested notes:
```bash
python cli.py ask "What is Block 1 goal?"
```

### 📝 3. Condense & Generate Cheat Sheets
Generate high-yield summaries for specific topics:
```bash
python cli.py condense "RAG Core"
```

### 🎯 4. Generate Interactive Quizzes
Generate multiple-choice quizzes (outputs formatted JSON / quiz text):
```bash
python cli.py quiz "RAG" --n 5
```

### ⏱️ 5. Deadline Triage Timetable
Generate an hour-by-hour study plan based on remaining time before your exam:
```bash
python cli.py triage --hours 6
```
