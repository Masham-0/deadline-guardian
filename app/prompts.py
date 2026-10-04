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
    """Build system and user prompts for answering a multi-part query with citations."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an expert AI exam-prep study buddy.\n"
        "Your task is to provide a comprehensive, step-by-step answer addressing EACH question/topic asked by the student using the provided Context Documents.\n"
        "Rules:\n"
        "1. Address each sub-topic or question explicitly under its own markdown heading (e.g. `## Round Robin`, `## fork() Function`, `## FCFS & Multilevel Queue`).\n"
        "2. Provide thorough explanations, definitions, mechanisms, and examples directly from the Context Documents.\n"
        "3. Include inline source citations [filename p.X] for key points and claims (e.g. [ch6.pptx p.20]).\n"
        "4. If a specific sub-topic is not mentioned anywhere in the Context Documents, state clearly under that heading that the uploaded materials do not cover it."
    )

    user_prompt = (
        f"Student Questions / Topics:\n{query}\n\n"
        f"Context Documents:\n{context_str}\n\n"
        f"Please provide a complete, structured study answer with inline citations [filename p.X]:"
    )
    return system_prompt, user_prompt


def build_triage_prompt(hours_left: float, triage_data: Dict[str, Any]) -> Tuple[str, str]:
    """Build system and user prompts for creating a multi-part deadline triage study plan."""
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
        "Construct a detailed, highly actionable, multi-part study plan based on the provided Syllabus, Past Papers, and Course Material.\n"
        "Structure your response strictly into these 3 sections:\n\n"
        "## 🎯 1. Exam Weightage & Priority Matrix\n"
        "Analyze past papers and syllabus evidence to divide all course topics into 3 priority tiers:\n"
        "- 🔴 **Tier 1: High-Yield Core (Must Know)** – High weightage / repeatedly tested topics.\n"
        "- 🟡 **Tier 2: Medium Priority (Should Know)** – Important supporting concepts.\n"
        "- 🟢 **Tier 3: Low Priority (Skip if Short on Time)** – Edge cases / low weightage.\n\n"
        "## ⏱️ 2. Hour-by-Hour Actionable Timetable\n"
        f"Divide the remaining {hours_left} hours into explicit time blocks (e.g. Hour 1-2, Hour 3, etc.) matching Tier 1 & 2 topics with study time and revision breaks.\n\n"
        "## 💡 3. High-Yield Revision Cheats & Citations\n"
        "List key formulas, definitions, and mechanisms to memorize for each Tier 1 topic, with inline citations [filename p.X]."
    )

    user_prompt = (
        f"Hours Remaining Before Exam: {hours_left} hours\n\n"
        f"Syllabus & Past Exam Paper Evidence:\n{syllabus_str}\n\n"
        f"Course Chapter Materials:\n{course_str}\n\n"
        f"Generate the 3-Part Panic Timetable Plan with inline citations [filename p.X]:"
    )
    return system_prompt, user_prompt
