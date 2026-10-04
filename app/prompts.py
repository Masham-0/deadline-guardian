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


def build_triage_prompt(hours_left: float, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for creating a detailed deadline triage study timetable."""
    context_str = format_context(chunks)

    system_prompt = (
        f"You are Deadline Guardian. The student has only {hours_left} hours left before their exam!\n"
        "Construct a detailed, realistic, high-efficiency study plan based on the provided Context Documents.\n"
        "Structure your output as:\n"
        "1. Executive Priority Matrix (Must-Know Core Concepts vs Nice-to-Know Detail)\n"
        "2. Hour-by-Hour Actionable Timetable (allocating exact time blocks)\n"
        "3. High-Yield Revision Summary & Exam Pitfalls to Avoid\n"
        "Include inline source citations [filename p.X] for referenced topics."
    )

    user_prompt = f"Hours Left: {hours_left} hours\n\nContext Documents:\n{context_str}\n\nGenerate the detailed Triage Study Plan:"
    return system_prompt, user_prompt
