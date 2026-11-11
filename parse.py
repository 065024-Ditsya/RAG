"""
ingestion/parse.py
-------------------
Converts every source document under data/<department>/ into clean Markdown,
saved under parsed/<department>/. Uses Docling for PDF, DOCX, and XLSX.

NOTE ON XLSX: Docling's own Excel conversion is used here as a first pass so
every file type is handled uniformly, but its raw table output was too
verbose for large spreadsheets, so xlsx_to_md.py is run AFTER this script
as a second pass to regenerate a cleaner, per-sheet Markdown for .xlsx files
specifically (see xlsx_to_md.py and Section 10.6 of the project report).

Run:
    python ingestion/parse.py
"""

from pathlib import Path

from docling.document_converter import DocumentConverter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PARSED_DIR = PROJECT_ROOT / "parsed"

DEPARTMENTS = ["HR", "Finance", "Legal", "Customer_Service", "IT"]
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}

converter = DocumentConverter()


def parse_file(file_path: Path, output_dir: Path) -> Path:
    """Convert a single document to Markdown and save it in output_dir."""
    result = converter.convert(str(file_path))
    markdown_text = result.document.export_to_markdown()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / (file_path.stem + ".md")
    out_path.write_text(markdown_text, encoding="utf-8")
    return out_path


def main():
    parsed_count = 0
    failed = []

    for dept in DEPARTMENTS:
        dept_data_dir = DATA_DIR / dept
        dept_parsed_dir = PARSED_DIR / dept

        if not dept_data_dir.exists():
            print(f"Skipping {dept} - no data folder found")
            continue

        files = [f for f in dept_data_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]

        for file_path in files:
            print(f"Parsing {file_path} ...")
            try:
                out_path = parse_file(file_path, dept_parsed_dir)
                print(f"   -> saved {out_path}")
                parsed_count += 1
            except Exception as exc:
                print(f"   !! FAILED: {file_path.name} ({exc})")
                failed.append(str(file_path))

    print(f"\nParsed {parsed_count} file(s).")
    if failed:
        print("Failed files:")
        for f in failed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
