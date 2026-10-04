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
