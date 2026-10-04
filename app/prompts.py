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
        formatted_blocks.append(f"[{idx}] Source: {source}, Page: {page}\n{text}")

    return "\n\n".join(formatted_blocks)


def build_ask_prompt(query: str, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for answering a query with citations."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an AI study buddy for last-minute exam prep.\n"
        "Your task is to answer the student's question relying STRICTLY and ONLY on the provided source context.\n"
        "Rules:\n"
        "1. You MUST cite your sources inline for key claims using the format [filename p.X] (e.g. [notes.pdf p.3]).\n"
        "2. If the provided context does not contain sufficient information to answer the question, state clearly: "
        "'The provided materials do not contain enough information to answer this question.'\n"
        "3. Do NOT extrapolate, hallucinate, or use outside knowledge not present in the context."
    )

    user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"
    return system_prompt, user_prompt


def build_condense_prompt(topic: str, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for creating a high-yield cheat sheet."""
    context_str = format_context(chunks)

    system_prompt = (
        "You are Deadline Guardian, an AI study buddy.\n"
        "Create a concise, high-yield cheat sheet / summary for the requested topic strictly using ONLY the provided context.\n"
        "Rules:\n"
        "1. Include key concepts, definitions, formulas, and bullet points.\n"
        "2. Include source citations [filename p.X] for key points.\n"
        "3. If the context does not cover the requested topic, state clearly that the material is insufficient.\n"
        "4. Do NOT use outside information."
    )

    topic_label = topic if topic else "All Course Materials"
    user_prompt = f"Context:\n{context_str}\n\nTopic to Condense: {topic_label}"
    return system_prompt, user_prompt


def build_quiz_prompt(topic: str, chunks: List[Dict[str, Any]], n_questions: int = 5) -> Tuple[str, str]:
    """Build system and user prompts for generating a multiple-choice quiz in JSON format."""
    context_str = format_context(chunks)

    system_prompt = (
        f"You are Deadline Guardian. Generate a quiz of exactly {n_questions} multiple-choice questions "
        "based strictly ONLY on the provided context.\n"
        "CRITICAL: Output ONLY raw valid JSON (a JSON array of objects). Do NOT wrap in markdown code blocks like ```json.\n"
        "Each object in the JSON list MUST follow this exact schema:\n"
        "[\n"
        "  {\n"
        '    "question": "Question text?",\n'
        '    "options": ["A) Choice 1", "B) Choice 2", "C) Choice 3", "D) Choice 4"],\n'
        '    "answer": "A",\n'
        '    "explanation": "Why this is correct (citing [filename p.X])"\n'
        "  }\n"
        "]\n"
        "If the context is insufficient to create questions, return an empty JSON array `[]`."
    )

    topic_label = topic if topic else "General Content"
    user_prompt = f"Context:\n{context_str}\n\nQuiz Topic: {topic_label}\nNumber of Questions: {n_questions}"
    return system_prompt, user_prompt


def build_triage_prompt(hours_left: float, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Build system and user prompts for creating a deadline triage study timetable."""
    context_str = format_context(chunks)

    system_prompt = (
        f"You are Deadline Guardian. The student has only {hours_left} hours left before their exam!\n"
        "Construct a realistic, high-efficiency, prioritized study plan based strictly ONLY on the provided course material context.\n"
        "Structure your output as:\n"
        "1. Executive Priority Matrix (Must-Know Core Concepts vs Nice-to-Know Detail)\n"
        "2. Hour-by-Hour Actionable Timetable\n"
        "3. High-Yield Revision Tips\n"
        "Include source citations [filename p.X] for referenced topics."
    )

    user_prompt = f"Hours Left: {hours_left} hours\n\nAvailable Materials Context:\n{context_str}"
    return system_prompt, user_prompt
