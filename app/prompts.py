from typing import List, Dict, Any, Tuple


def format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved context chunks with source and page citations."""
    if not chunks:
        return "(No relevant source context available.)"

    formatted_blocks = []
    for idx, chunk in enumerate(chunks, start=1):
        source = chunk.get("source", "unknown")
        page = chunk.get("page", 1)
        text = chunk.get("text", "").strip()
        formatted_blocks.append(f"--- Document [{source} (Page {page})] ---\n{text}")

    return "\n\n".join(formatted_blocks)


def build_ask_prompt(query: str, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for answering a query with hybrid RAG + knowledge base synthesis."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an expert AI exam-prep study buddy.\n"
        "Your sole task is to answer ONLY the exact question/topic asked by the student.\n"
        "Rules:\n"
        "1. STRICT FOCUSED SCOPE: Answer the student's exact question DIRECTLY under a clear main heading (e.g. `## Structural Classification of Proteins`). IGNORE and FILTER OUT any surrounding background text from the context documents (such as general elemental composition, unrelated introduction paragraphs, or adjacent topics like nucleic acids) that do not directly answer the user prompt.\n"
        "2. MATHEMATICAL LAWS & FORMULAS: For theoretical laws, speedup formulas, and math equations (e.g. Amdahl's Law, Little's Law, CPU Speedup), ALWAYS write the exact equation in LaTeX display format `$$ ... $$` (e.g. $$ S_{latency}(s) = \\frac{1}{(1-f) + \\frac{f}{s}} $$). DO NOT generate Python or pseudocode for mathematical formulas unless code is explicitly asked.\n"
        "3. CODE & ALGORITHMS: For programming algorithms or process synchronization solutions (e.g. Peterson's Solution, CPU scheduling, Semaphores, System Calls), match the programming language in the uploaded Context Documents (default to C/C++ ` ```c ... ``` ` if C/C++ is used in context notes). Output full, compilable, production-ready code with complete variable declarations, loops, entry/exit sections, and comments. DO NOT write LaTeX algorithm environments (`\\begin{algorithm}`, `\\begin{algorithmic}`, `\\State`, `\\texttt`).\n"
        "4. EXHAUSTIVE ENUMERATION: If the prompt explicitly asks for a list or classification of items, list ALL requested items in a clean Markdown table or numbered list.\n"
        "5. KNOWLEDGE BASE & RELEVANCE: Ground definitions in the provided Context Documents with inline citations `[filename p.X]`. If context notes lack full code or formulas, use your internal AI knowledge base to complete them. NEVER state 'I cannot access external databases' or 'I don't have internet access'.\n"
        "6. Do NOT prefix output with filler like 'Sure, here is the requested structured response'."
    )

    user_prompt = (
        f"Student Questions / Topics Requested:\n{query}\n\n"
        f"Context Documents:\n{context_str}\n\n"
        f"Provide a structured, focused answer addressing ONLY the requested topic above using LaTeX math `$$...$$` for formulas, C/C++ code blocks ````c```` for algorithms, and relevant inline citations [filename p.X]:"
    )
    return system_prompt, user_prompt


def build_triage_pass1_prompt(hours_left: float, triage_data: Dict[str, Any]) -> Tuple[str, str]:
    """Pass 1: Build priority matrix & hour-by-hour timetable."""
    syllabus_chunks = triage_data.get("syllabus_chunks", [])
    course_chunks = triage_data.get("course_chunks", [])
    all_chunks = triage_data.get("all_chunks", [])

    if not syllabus_chunks and not course_chunks:
        syllabus_str = format_context(all_chunks)
        course_str = ""
    else:
        syllabus_str = format_context(syllabus_chunks)
        course_str = format_context(course_chunks)

    system_prompt = (
        f"You are Deadline Guardian. The student has ONLY {hours_left} hours left before their exam!\n"
        "Construct Pass 1 of a high-yield deadline study plan based on Syllabus, Past Papers, and Course Material.\n"
        "Structure your response strictly into these 2 sections:\n\n"
        "## 🎯 1. Exam Weightage & Priority Matrix\n"
        "Divide all course topics into 3 explicit priority tiers based on exam evidence:\n"
        "- 🔴 **Tier 1: High-Yield Core (Must Know)** – Repeatedly tested / heavy mark weightage topics.\n"
        "- 🟡 **Tier 2: Medium Priority (Should Know)** – Important supporting concepts.\n"
        "- 🟢 **Tier 3: Low Priority (Skip if Short on Time)** – Edge cases / low weightage.\n\n"
        "## ⏱️ 2. Hour-by-Hour Actionable Timetable\n"
        f"Divide the remaining {hours_left} hours into explicit time blocks (e.g. Hour 1-2, Hour 3, etc.) allocating time according to topic priority."
    )

    user_prompt = (
        f"Hours Remaining Before Exam: {hours_left} hours\n\n"
        f"Syllabus & Past Exam Paper Evidence:\n{syllabus_str}\n\n"
        f"Course Chapter Overview:\n{course_str}\n\n"
        f"Generate Section 1 (Priority Matrix) and Section 2 (Hour-by-Hour Timetable):"
    )
    return system_prompt, user_prompt


def build_triage_pass2_prompt(hours_left: float, topic_batch: List[str], chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Pass 2: Deep dive into high-yield topics to write detailed revision cheats."""
    context_str = format_context(chunks)
    topics_list_str = "\n".join([f"- {t}" for t in topic_batch])

    system_prompt = (
        "You are Deadline Guardian.\n"
        "Provide a deep-dive, comprehensive High-Yield Revision Cheatsheet for the following high-priority topics.\n"
        "Rules:\n"
        "1. For EACH topic listed below, create a dedicated sub-heading (e.g. `### Topic Name`).\n"
        "2. Provide key definitions, core equations/formulas, step-by-step algorithms, and crucial exam tips.\n"
        "3. Include inline citations `[filename p.X]` for document references, and use your AI knowledge base to elaborate fully so the student can memorize and understand them immediately."
    )

    user_prompt = (
        f"High-Priority Topics to Expand:\n{topics_list_str}\n\n"
        f"Focused Context Documents:\n{context_str}\n\n"
        f"Generate ## 💡 3. High-Yield Revision Cheats & Deep-Dive Notes:"
    )
    return system_prompt, user_prompt
