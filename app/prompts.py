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
    """Build system and user prompts for answering a query with citations."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an AI exam-prep study buddy.\n"
        "Your task is to answer the student's question thoroughly using the information in the provided Context Documents.\n"
        "Rules:\n"
        "1. Cite your sources inline for key points using the format [filename p.X] (e.g. [ch6.pptx p.20]).\n"
        "2. Use all relevant details and definitions found across the Context Documents.\n"
        "3. Only if the Context Documents contain zero information about the question, state that the materials do not cover it."
    )

    user_prompt = (
        f"Question: {query}\n\n"
        f"Context Documents:\n{context_str}\n\n"
        f"Please provide a clear answer to the question '{query}' using the Context Documents above, including inline citations [filename p.X]:"
    )
    return system_prompt, user_prompt


def build_condense_prompt(topic: str, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for creating a high-yield cheat sheet."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an AI study buddy.\n"
        "Create a concise, high-yield cheat sheet / summary for the requested topic using the provided Context Documents.\n"
        "Rules:\n"
        "1. Include key concepts, definitions, formulas, and bullet points.\n"
        "2. Include inline source citations [filename p.X] for key points.\n"
        "3. Focus on high-yield exam information."
    )

    topic_label = topic if topic else "All Course Materials"
    user_prompt = f"Topic to Condense: {topic_label}\n\nContext Documents:\n{context_str}\n\nGenerate the Cheat Sheet with citations:"
    return system_prompt, user_prompt


def build_quiz_prompt(topic: str, chunks: List[Dict[str, Any]], n_questions: int = 5) -> Tuple[str, str]:
    """Build system and user prompts for generating a multiple-choice quiz in JSON format."""
    context_str = format_context(chunks)

    system_prompt = (
        f"You are Deadline Guardian. Generate a quiz of exactly {n_questions} multiple-choice questions "
        "based on the provided Context Documents.\n"
        "CRITICAL: Output ONLY raw valid JSON (a JSON array of objects). Do NOT wrap in markdown code blocks like ```json.\n"
        "Each object in the JSON list MUST follow this exact schema:\n"
        "[\n"
        "  {\n"
        '    "question": "Question text?",\n'
        '    "options": ["A) Choice 1", "B) Choice 2", "C) Choice 3", "D) Choice 4"],\n'
        '    "answer": "A",\n'
        '    "explanation": "Why this is correct (citing [filename p.X])"\n'
        "  }\n"
        "]"
    )

    topic_label = topic if topic else "General Content"
    user_prompt = f"Quiz Topic: {topic_label}\nNumber of Questions: {n_questions}\n\nContext Documents:\n{context_str}\n\nGenerate raw JSON quiz array:"
    return system_prompt, user_prompt


def build_triage_prompt(hours_left: float, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for creating a deadline triage study timetable."""
    context_str = format_context(chunks)

    system_prompt = (
        f"You are Deadline Guardian. The student has only {hours_left} hours left before their exam!\n"
        "Construct a realistic, high-efficiency, prioritized study plan based on the provided Context Documents.\n"
        "Structure your output as:\n"
        "1. Executive Priority Matrix (Must-Know Core Concepts vs Nice-to-Know Detail)\n"
        "2. Hour-by-Hour Actionable Timetable\n"
        "3. High-Yield Revision Tips\n"
        "Include source citations [filename p.X] for referenced topics."
    )

    user_prompt = f"Hours Left: {hours_left} hours\n\nContext Documents:\n{context_str}\n\nGenerate the Triage Study Timetable:"
    return system_prompt, user_prompt
