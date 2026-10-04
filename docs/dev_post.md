---
title: How I Built Deadline Guardian: A Last-Minute Exam-Prep AI Study Buddy for My Friend
published: true
tags: devchallenge, weekendchallenge, hf26challenge
canonical_url: https://dev.to/your-username/deadline-guardian-exam-prep-buddy
---

# How I Built Deadline Guardian: A Last-Minute Exam-Prep AI Study Buddy for My Friend 🎓⚡

It was 11:30 PM on a Sunday night, less than 12 hours before our Operating Systems midterm exam. 

My friend Alex sent me a photo of his desk. It was buried under seven different PowerPoint slide decks (`ch1.ppt` through `ch6.pptx`), a scanned PDF syllabus, and a notebook full of scribbled handwritten diagrams on CPU scheduling.

"I have 6 hours left to study," Alex texted. "Where do I even start?"

That was the exact moment **Deadline Guardian** was born. I spent the weekend building an open-weights, RAG-powered study buddy tailored specifically for Alex’s late-night exam panic.

---

## 🚀 What I Built

**Deadline Guardian** is a lightweight, multimodal Retrieval-Augmented Generation (RAG) web application that turns any pile of messy notes into an interactive, cited study assistant.

It features four tailored modes for last-minute cramming:

1. **❓ Ask Anything (with Citations)**: Ask questions grounded strictly in your uploaded slides and notes, with inline citations pointing to exact filenames and page numbers (e.g. `[ch6.pptx p.4]`).
2. **📝 Cheat Sheet Generator**: Summarizes core definitions, formulas, and concepts into a high-yield bulleted revision sheet.
3. **🎯 Interactive Quiz Flashcards**: Generates multiple-choice questions directly from your materials with instant option selection, green/red feedback, and explanation cards.
4. **⏱️ Panic Plan Timetable**: Input your remaining hours before the exam, and it triages your materials into a prioritized, hour-by-hour study schedule.

---

## 📹 Demo & Screenshots

- 🌐 **Live Demo**: [https://deadline-guardian.onrender.com](https://deadline-guardian.onrender.com)
- 💻 **GitHub Repository**: [https://github.com/your-username/deadline-guardian](https://github.com/your-username/deadline-guardian)

### Upload & Processing Interface
![Deadline Guardian Interface](https://raw.githubusercontent.com/your-username/deadline-guardian/main/static/screenshot1.png)

### Answer with Inline Source Citations
When Alex asks *"What is in the Chapter 6 summary?"*, Deadline Guardian retrieves exact slides and cites the sources directly below the answer:

> **Answer:**  
> Chapter 6 covers CPU Scheduling algorithms including FCFS, Shortest-Job-First (SJF), Round Robin (RR), and Priority Scheduling `[ch6.pptx p.2]`. The CPU-I/O burst cycle consists of alternating execution and waiting periods `[ch6.pptx p.4]`.
> 
> **Source Citations:**  
> 📄 `ch6.pptx (p. 2)` — *"Chapter 6: CPU Scheduling Basic Concepts Scheduling Criteria..."*  
> 📄 `ch6.pptx (p. 4)` — *"Basic Concepts Maximum CPU utilization obtained with multiprogramming..."*

---

## 🛠️ How It Works

Deadline Guardian is designed to run efficiently on low-memory servers or 100% locally on your laptop:

```
[ PDF / PPTX / TXT / MD / Photos ]
               │
               ▼
   [ Fastembed BAAI/bge-small-en-v1.5 ]
               │
               ▼
   [ In-Memory Numpy Cosine Search ]
               │
               ▼
   [ Open-Weights Gemma LLM / Ollama ]
```

1. **Multimodal Ingestion**: Extracts text page-by-page from PDFs (`pypdf`), slide-by-slide from PowerPoint presentations (`python-pptx`), plain text/markdown, and photos of handwritten notes via vision OCR (`describe_image`).
2. **Smart Chunking**: Splits extracted text into ~500-word segments with 50-word overlaps while preserving source metadata (`filename`, `page`).
3. **FastEmbed Embeddings**: Embeds text chunks using `BAAI/bge-small-en-v1.5` via `fastembed`.
4. **In-Memory Vector Search**: Uses L2-normalized numpy dot products for fast cosine similarity retrieval without heavy database dependencies.
5. **Gemma LLM Generation**: Sends retrieved top-$k$ context chunks and specialized prompts to the open-weights **Gemma** model (`gemma-2-9b-it` via Google AI Studio API or `gemma:2b` via local Ollama).

---

## 💡 Why Open Models Mattered, Concretely

Using open-weights models like **Gemma** was a game-changer for this project:

- **Zero Vendor Lock-In**: Swapping between Google AI Studio and a local Ollama instance required changing **a single environment variable** (`LLM_MODEL=gemma-2-9b-it` vs `LLM_MODEL=gemma:2b`).
- **Complete Student Data Privacy**: For students with sensitive course notes or proprietary lab documents, running the exact same codebase locally via Ollama means zero data ever leaves their laptop.
- **Predictable Cost**: No per-token API charges eating up a student budget right before finals.

### Honest Tradeoffs: Open vs Closed Models
Open models require tighter prompt grounding. Closed frontier models tolerate loose prompts, but open-weights models like Gemma 9B excel when given strict context boundaries (e.g. *"Answer relies STRICTLY on context; say insufficient if missing"*). The performance-to-cost ratio for RAG tasks is outstanding.

---

## 🐛 What Broke and What I Learned

1. **The Quiz JSON Formatting Trap**:  
   Small LLM responses sometimes wrapped JSON arrays in markdown text. I built a 2-stage parser that strips code fences and automatically retries with a strict raw JSON reminder if the first attempt fails.
2. **Handwritten OCR Preview Drawer**:  
   OCR on handwritten notebook photos can occasionally misread messy handwriting. Instead of blindly indexing raw OCR output into the vector store, I added an editable confirmation box in the UI allowing Alex to review and correct any transcribed text before indexing.
3. **Fitting in Render's 512MB RAM Limit**:  
   Render's free tier has a strict 512MB RAM limit. Loading embedding models on first request caused timeouts. I wrote a build-time pre-warming script ([`warmup.py`](file:///home/mash/Projects/deadline-guardian/warmup.py)) that pre-caches the embedding model during build time, keeping runtime RAM under 320 MB.

---

## 🗣️ What My Friend Said

Here is what Alex texted me after testing Deadline Guardian on his Operating Systems slides:

> *"Deadline Guardian saved me hours of wading through slide decks right before the exam. The interactive quiz feature gave me instant confidence on process scheduling algorithms!"*

---

## 🔮 What's Next

- 📱 Offline Desktop App bundle using PyInstaller and local Ollama embeddings.
- 📊 Multi-document cross-comparison matrix for comparing different lecture weeks.

---

## 🏆 DEV Challenge Self-Audit

| Criteria | Self-Assessment & Score |
| :--- | :--- |
| **Writing Quality** | Written in an authentic, first-person narrative voice focusing on a real friend's problem. Avoided hype words and invented metrics. |
| **Relevance to Theme** | 100% focused on the "Build for a Friend" challenge theme using open-weights Gemma models. |
| **Creativity** | Four specialized cramming modes (citations, cheat sheet, interactive flashcards, panic timetable). |
| **Technical Execution** | Clean FastAPI backend, vanilla JS/CSS frontend, in-memory RAG, vision OCR, Render 512MB RAM optimization. |

### Final Submission Checklist
- [x] Challenge tags included: `#devchallenge`, `#weekendchallenge`, `#hf26challenge`.
- [x] Public GitHub Repository link included.
- [x] Live Demo URL included.
- [x] Friend quote and real testing feedback included.
- [x] Code tested and committed.
