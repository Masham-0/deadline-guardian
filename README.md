# deadline-guardian 🛡️⚡

A last-minute study buddy. Upload your notes, slides, PDFs (and photos of handwritten pages), then ask questions, get a cheat sheet, or get a panic plan for the hours you have left.

Built by **Mohammad Masham** for the **DEV Hacktoberfest Weekend Challenge** *"Build for a Friend"*.

- **Developer:** Mohammad Masham ([mohd.masham@gmail.com](mailto:mohd.masham@gmail.com))
- **College:** Netaji Subhas University of Technology (NSUT)
- **Live demo:** [https://deadline-guardian.onrender.com](https://deadline-guardian.onrender.com) *(free tier, may take ~30s to wake up)*
- **Write-up:** [DEV Community Post](#)

---

## ⚡ What it does
- **Ask** – Answers questions strictly from *your* uploaded notes with exact inline source citations (`[filename p.X]`).
- **Cheat Sheet** – Condenses dense lecture notes and slides into a high-yield revision sheet.
- **Panic Plan** – Tell it how many hours you have left before the exam; it auto-prioritizes topics and constructs an hour-by-hour study timetable.
- **Multi-Format Support** – Reads PDFs (scanned & digital), PowerPoint decks (`.pptx`), text notes (`.txt`, `.md`), and photos/diagrams (`.jpg`, `.png`, `.webp`).

---

## 🧠 How it works
1. **Multi-Format Ingestion**: Files are parsed into clean text. Scanned pages or photos undergo vision transcription if supported by the model API endpoint.
2. **Paragraph-Aware Chunking**: Text is split into fine-grained 150-word paragraph-aware chunks with overlap to preserve conceptual context.
3. **Local Vector Embeddings**: Chunks are embedded in-memory using `BAAI/bge-small-en-v1.5` cosine similarity embeddings (`fastembed`).
4. **Targeted Vector Retrieval**: User queries execute cosine similarity search over session embeddings to retrieve top relevant contexts (`top-k`).
5. **Grounded Synthesis & Streaming**: Retrieved contexts and query are streamed from an open-weights LLM model (Gemma) with LaTeX math rendering (`KaTeX`).

App and retrieval run on FastAPI & Uvicorn (Render free tier friendly, < 350MB RAM). The LLM is called through an OpenAI-compatible API, so you can swap models by changing one env var, or run everything locally with Ollama.

---

## 🚀 Run locally

### 1. Prerequisites & Environment Setup
```bash
git clone https://github.com/your-username/deadline-guardian.git
cd deadline-guardian

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit your `.env` file:
```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_google_ai_studio_or_openai_api_key
LLM_MODEL=gemma-2-9b-it
```

### 3. Start the Local Server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

### Environment variables
| Name | Description | Example |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `LLM_API_KEY` | API authentication key | `your_api_key` |
| `LLM_MODEL` | Gemma or open-weights model name | `gemma-2-9b-it` |
| `HF_TOKEN` | Hugging Face token (optional) | `hf_...` |

---

### Fully local with Ollama
To run 100% locally and offline without external API keys:

1. Install [Ollama](https://ollama.com) and pull the model:
   ```bash
   ollama pull gemma:2b
   ```

2. Run the application with Ollama environment settings:
   ```bash
   LLM_BASE_URL=http://localhost:11434/v1 LLM_API_KEY=ollama LLM_MODEL=gemma:2b uvicorn main:app --reload
   ```

---

## 💻 Terminal CLI Mode
You can also run Deadline Guardian directly from the command line:
```bash
# Ingest notes from a directory
python cli.py ingest samples/

# Ask questions directly
python cli.py ask "Explain Peterson's Solution"

# Generate a 6-hour deadline panic timetable
python cli.py triage --hours 6
```

---

## ⚠️ Limitations
- Sessions are stored in-memory and reset after ~2 hours of inactivity or a server restart.
- Handwriting and diagram reading require a vision-capable LLM model endpoint.
- Free hosting (Render) sleeps when idle (~30s cold start).

---

## 👤 Author
- **Mohammad Masham** ([mohd.masham@gmail.com](mailto:mohd.masham@gmail.com))
- **College:** Netaji Subhas University of Technology (NSUT)
- Created for **DEV Hacktoberfest Weekend Challenge 2026** *"Build for a Friend"*.

---

## 📄 License
[MIT License](LICENSE)
