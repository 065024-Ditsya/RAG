"""
ingestion/xlsx_to_md.py
------------------------
Second-pass converter for Excel workbooks. Docling's default .xlsx-to-Markdown
output was excessively verbose for large spreadsheets (in one documented case,
a single workbook produced a 942-line Markdown file with an embedded 900-row
log dumped verbatim), which hurt retrieval precision. This script regenerates
a much cleaner Markdown version instead: each sheet gets its own heading and a
proper Markdown table, so LlamaIndex's MarkdownNodeParser can chunk it
sensibly (one chunk per sheet/table) rather than splitting an unstructured
wall of text.

This OVERWRITES the corresponding parsed/<department>/<file>.md that
parse.py produced for any .xlsx source file. Run this AFTER parse.py.

Run:
    python ingestion/xlsx_to_md.py
"""

from pathlib import Path

import openpyxl
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PARSED_DIR = PROJECT_ROOT / "parsed"

DEPARTMENTS = ["HR", "Finance", "Legal", "Customer_Service", "IT"]


def sheet_to_markdown_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavoured Markdown table."""
    df = df.fillna("")
    headers = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for _, row in df.iterrows():
        cells = [str(v) for v in row.tolist()]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def convert_workbook(xlsx_path: Path) -> str:
    """Convert every sheet in a workbook into its own Markdown section."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    sections = [f"# {xlsx_path.stem}"]

    for sheet_name in wb.sheetnames:
        try:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        except Exception as exc:
            print(f"   !! could not read sheet '{sheet_name}': {exc}")
            continue
        if df.empty:
            continue
        sections.append(f"\n## Sheet: {sheet_name}\n")
        sections.append(sheet_to_markdown_table(df))

    return "\n".join(sections)


def main():
    converted = 0

    for dept in DEPARTMENTS:
        dept_data_dir = DATA_DIR / dept
        dept_parsed_dir = PARSED_DIR / dept
        if not dept_data_dir.exists():
            continue

        for xlsx_path in dept_data_dir.glob("*.xlsx"):
            print(f"Converting {xlsx_path} ...")
            try:
                markdown_text = convert_workbook(xlsx_path)
            except Exception as exc:
                print(f"   !! FAILED: {xlsx_path.name} ({exc})")
                continue

            dept_parsed_dir.mkdir(parents=True, exist_ok=True)
            out_path = dept_parsed_dir / (xlsx_path.stem + ".md")
            out_path.write_text(markdown_text, encoding="utf-8")
            print(f"   -> overwrote {out_path} ({len(markdown_text.splitlines())} lines)")
            converted += 1

    print(f"\nConverted {converted} workbook(s).")


if __name__ == "__main__":
    main()
