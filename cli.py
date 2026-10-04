import sys
import json
import argparse
from pathlib import Path

from app.ingest import ingest_directory, extract_text, SUPPORTED_EXTENSIONS
from app.rag import chunk_text, add_to_store, retrieve, save_store, load_store
from app.llm import chat
from app import prompts


STORE_FILE = ".store.pkl"


def handle_ingest(args):
    path = Path(args.folder)
    if not path.exists():
        print(f"Error: Path '{args.folder}' does not exist.")
        sys.exit(1)

    load_store(STORE_FILE)

    print(f"Ingesting material from: {path} ...")
    if path.is_file():
        extracted = extract_text(path)
    else:
        extracted = ingest_directory(path)

    if not extracted:
        print("No readable text found in the specified path.")
        return

    chunks = chunk_text(extracted, chunk_size=500, chunk_overlap=50)
    total_chunks = add_to_store(args.session, chunks)
    save_store(STORE_FILE)

    print(f"Successfully processed {len(extracted)} page/slide segments into {len(chunks)} text chunks.")
    print(f"Session '{args.session}' now contains {total_chunks} total stored chunks.")


def handle_ask(args):
    load_store(STORE_FILE)
    chunks = retrieve(args.session, args.query, k=args.k)

    if not chunks:
        print(f"No stored material found for session '{args.session}'. Run `python cli.py ingest <folder>` first.")
        return

    sys_prompt, user_prompt = prompts.build_ask_prompt(args.query, chunks)
    print("\n--- Deadline Guardian Answer ---")
    response = chat(sys_prompt, user_prompt)
    print(response)
    print("--------------------------------\n")


def handle_condense(args):
    load_store(STORE_FILE)
    search_query = args.topic if args.topic else "core concepts summary"
    chunks = retrieve(args.session, search_query, k=args.k)

    if not chunks:
        print(f"No stored material found for session '{args.session}'. Run `python cli.py ingest <folder>` first.")
        return

    sys_prompt, user_prompt = prompts.build_condense_prompt(args.topic, chunks)
    print("\n--- Cheat Sheet ---")
    response = chat(sys_prompt, user_prompt)
    print(response)
    print("-------------------\n")


def handle_quiz(args):
    load_store(STORE_FILE)
    search_query = args.topic if args.topic else "key definitions exam questions"
    chunks = retrieve(args.session, search_query, k=args.k)

    if not chunks:
        print(f"No stored material found for session '{args.session}'. Run `python cli.py ingest <folder>` first.")
        return

    sys_prompt, user_prompt = prompts.build_quiz_prompt(args.topic, chunks, n_questions=args.n)
    print(f"\n--- Generating Quiz ({args.n} Questions) ---")
    raw_response = chat(sys_prompt, user_prompt)

    # Clean potential markdown wrapping if returned by LLM
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        quiz_data = json.loads(cleaned)
        if isinstance(quiz_data, list):
            for i, q in enumerate(quiz_data, start=1):
                print(f"\nQ{i}: {q.get('question')}")
                for opt in q.get('options', []):
                    print(f"   {opt}")
                print(f"Answer: {q.get('answer')}")
                print(f"Explanation: {q.get('explanation')}")
        else:
            print(raw_response)
    except Exception:
        # Fallback to raw text output if JSON parsing fails
        print(raw_response)

    print("-------------------------------------------\n")


def handle_triage(args):
    load_store(STORE_FILE)
    chunks = retrieve(args.session, "syllabus exam core topics overview important", k=args.k)

    if not chunks:
        print(f"No stored material found for session '{args.session}'. Run `python cli.py ingest <folder>` first.")
        return

    sys_prompt, user_prompt = prompts.build_triage_prompt(args.hours, chunks)
    print(f"\n--- Deadline Triage Plan ({args.hours} Hours Remaining) ---")
    response = chat(sys_prompt, user_prompt)
    print(response)
    print("-----------------------------------------------------------\n")


def main():
    parser = argparse.ArgumentParser(
        description="Deadline Guardian: Last-minute exam-prep study buddy (CLI)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-command to execute")

    # Ingest command
    parser_ingest = subparsers.add_parser("ingest", help="Ingest notes from a folder or file")
    parser_ingest.add_argument("folder", help="Folder or file path to ingest")
    parser_ingest.add_argument("--session", default="default", help="Session ID")
    parser_ingest.set_defaults(func=handle_ingest)

    # Ask command
    parser_ask = subparsers.add_parser("ask", help="Ask a question about your ingested materials")
    parser_ask.add_argument("query", help="Question to ask")
    parser_ask.add_argument("--session", default="default", help="Session ID")
    parser_ask.add_argument("--k", type=int, default=6, help="Number of retrieved context chunks")
    parser_ask.set_defaults(func=handle_ask)

    # Condense command
    parser_condense = subparsers.add_parser("condense", help="Generate a cheat sheet summary for a topic")
    parser_condense.add_argument("topic", nargs="?", default="", help="Topic to summarize (optional)")
    parser_condense.add_argument("--session", default="default", help="Session ID")
    parser_condense.add_argument("--k", type=int, default=8, help="Number of retrieved context chunks")
    parser_condense.set_defaults(func=handle_condense)

    # Quiz command
    parser_quiz = subparsers.add_parser("quiz", help="Generate quiz questions on a topic")
    parser_quiz.add_argument("topic", nargs="?", default="", help="Topic for quiz (optional)")
    parser_quiz.add_argument("--n", type=int, default=5, help="Number of questions")
    parser_quiz.add_argument("--session", default="default", help="Session ID")
    parser_quiz.add_argument("--k", type=int, default=8, help="Number of retrieved context chunks")
    parser_quiz.set_defaults(func=handle_quiz)

    # Triage command
    parser_triage = subparsers.add_parser("triage", help="Generate a prioritized study timetable")
    parser_triage.add_argument("--hours", type=float, default=6.0, help="Hours left before exam")
    parser_triage.add_argument("--session", default="default", help="Session ID")
    parser_triage.add_argument("--k", type=int, default=10, help="Number of retrieved context chunks")
    parser_triage.set_defaults(func=handle_triage)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
