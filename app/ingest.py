import os
from pathlib import Path
from typing import List, Dict, Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None


SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".txt", ".md"}


def extract_text(file_path: str | Path) -> List[Dict[str, Any]]:
    """
    Extract text content from a single file.
    Returns a list of dicts: [{"text": str, "source": str, "page": int | str}]
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    source_name = path.name

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}' for '{source_name}'. "
            f"Supported formats are: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    results: List[Dict[str, Any]] = []

    try:
        if suffix == ".pdf":
            if PdfReader is None:
                raise ImportError("pypdf is required to parse PDF files. Run `pip install pypdf`.")
            
            reader = PdfReader(path)
            for idx, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                cleaned = text.strip()
                if cleaned:
                    results.append({"text": cleaned, "source": source_name, "page": idx})

        elif suffix == ".pptx":
            if Presentation is None:
                raise ImportError("python-pptx is required to parse PPTX files. Run `pip install python-pptx`.")

            prs = Presentation(path)
            for idx, slide in enumerate(prs.slides, start=1):
                slide_texts = []
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text_frame:
                        slide_texts.append(shape.text_frame.text)
                combined = "\n".join(slide_texts).strip()
                if combined:
                    results.append({"text": combined, "source": source_name, "page": idx})

        elif suffix in (".txt", ".md"):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")
            
            cleaned = content.strip()
            if cleaned:
                results.append({"text": cleaned, "source": source_name, "page": 1})

    except Exception as e:
        if isinstance(e, (ValueError, ImportError, FileNotFoundError)):
            raise e
        raise ValueError(f"Failed to extract text from '{source_name}': {str(e)}") from e

    return results


def ingest_directory(dir_path: str | Path) -> List[Dict[str, Any]]:
    """
    Recursively extract text from all supported files (.pdf, .pptx, .txt, .md) in a directory.
    """
    directory = Path(dir_path)
    if not directory.is_dir():
        raise NotADirectoryError(f"Directory not found: {dir_path}")

    all_extracted: List[Dict[str, Any]] = []
    
    for root, _, files in os.walk(directory):
        for file in sorted(files):
            file_path = Path(root) / file
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    extracted = extract_text(file_path)
                    all_extracted.extend(extracted)
                except Exception as err:
                    print(f"[Warning] Skipping {file_path.name}: {err}")

    return all_extracted
