
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Zotero PDF -> Markdown

Fast path:
    PyMuPDF: normal text-based PDFs

Fallback:
    Docling: multi-column PDFs, tables, scanned PDFs,
             or PDFs with poor text extraction

Features:
    - Recursive PDF discovery
    - Preserve original directory structure
    - Original absolute PDF path in Markdown header
    - No image export
    - Incremental conversion using file size + mtime
    - Skip unchanged converted PDFs
    - Retry failed PDFs on next run
    - Atomic Markdown writing
    - Conversion logs
"""

import json
import time
import traceback
from pathlib import Path

import pymupdf


# ============================================================
# 1. USER CONFIGURATION
# ============================================================

PDF_INPUT = Path("INPUT/FOLDER").expanduser()
MD_OUTPUT = Path("OUTPUT/FOLDER").expanduser()

# True: skip unchanged PDFs already converted
# False: reconvert all PDFs
SKIP_EXISTING = True

# Use Docling for PDFs with detected complex layouts/tables
ENABLE_DOCLING = True

# Enable OCR in Docling fallback for scanned PDFs
ENABLE_OCR = True

# ============================================================
# 2. INITIALIZATION
# ============================================================

PDF_INPUT = PDF_INPUT.resolve()
MD_OUTPUT = MD_OUTPUT.resolve()

if not PDF_INPUT.is_dir():
    raise SystemExit(f"Input directory does not exist: {PDF_INPUT}")

MD_OUTPUT.mkdir(parents=True, exist_ok=True)

MANIFEST_FILE = MD_OUTPUT / "_conversion_manifest.json"
FAILURE_LOG = MD_OUTPUT / "_conversion_failures.txt"
TIME_LOG = MD_OUTPUT / "_conversion_times.tsv"

if MANIFEST_FILE.exists():
    try:
        manifest = json.loads(
            MANIFEST_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        print("WARNING: Manifest cannot be read. Starting a new one.")
        manifest = {}
else:
    manifest = {}


def save_manifest():
    """Atomically save conversion records."""

    temp_file = MANIFEST_FILE.with_suffix(".tmp")

    temp_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    temp_file.replace(MANIFEST_FILE)


# ============================================================
# 3. PDF DISCOVERY
# ============================================================

pdf_files = sorted(
    p for p in PDF_INPUT.rglob("*")
    if p.is_file() and p.suffix.lower() == ".pdf"
)

print("=" * 65)
print("ZOTERO PDF -> MARKDOWN")
print("=" * 65)
print(f"Input : {PDF_INPUT}")
print(f"Output: {MD_OUTPUT}")
print(f"PDFs  : {len(pdf_files)}")
print("=" * 65)

if not pdf_files:
    raise SystemExit("No PDF files found.")


# ============================================================
# 4. LAYOUT DETECTION
# ============================================================

def detect_two_columns(page):
    """
    Heuristic detection of two-column text layout.

    This is a screening heuristic, not a perfect layout classifier.
    """

    width = page.rect.width
    height = page.rect.height
    midpoint = width / 2

    blocks = page.get_text("blocks")

    left_blocks = []
    right_blocks = []

    for block in blocks:

        if len(block) < 5:
            continue

        x0, y0, x1, y1, text = block[:5]

        if not isinstance(text, str) or len(text.strip()) < 30:
            continue

        # Ignore blocks spanning most of the page width
        if (x1 - x0) > width * 0.75:
            continue

        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2

        if center_x < midpoint - width * 0.08:
            left_blocks.append((center_y, y0, y1))

        elif center_x > midpoint + width * 0.08:
            right_blocks.append((center_y, y0, y1))

    if len(left_blocks) < 3 or len(right_blocks) < 3:
        return False

    # Check whether the two sides contain text at similar vertical positions
    for left in left_blocks:
        for right in right_blocks:

            if abs(left[0] - right[0]) < height * 0.30:
                return True

    return False


def detect_tables(page):
    """
    Detect tables using PyMuPDF's table finder.
    Only used as a screening step.
    """

    try:
        tables = page.find_tables()
        return len(tables.tables) > 0

    except Exception:
        return False


# ============================================================
# 5. FAST EXTRACTION USING PYMUPDF
# ============================================================

def extract_with_pymupdf(pdf_path):
    """
    Extract text from a relatively simple PDF.

    Returns:
        markdown_text, requires_docling, reason
    """

    page_texts = []
    requires_docling = False
    reasons = []

    doc = pymupdf.open(pdf_path)

    try:

        if doc.is_encrypted:
            raise RuntimeError("Encrypted PDF")

        for page_number, page in enumerate(doc, 1):

            text = page.get_text("text", sort=True).strip()

            # Basic text quality checks
            if len(text) < 40:
                requires_docling = True
                reasons.append(
                    f"Page {page_number}: insufficient text"
                )

            if text:
                replacement_ratio = (
                    text.count("\ufffd") / max(len(text), 1)
                )

                if replacement_ratio > 0.01:
                    requires_docling = True
                    reasons.append(
                        f"Page {page_number}: text encoding problems"
                    )

            # Check whether the page is likely multi-column
            if detect_two_columns(page):
                requires_docling = True
                reasons.append(
                    f"Page {page_number}: possible two-column layout"
                )

            # Check for structured tables
            if detect_tables(page):
                requires_docling = True
                reasons.append(
                    f"Page {page_number}: possible table detected"
                )

            if text:
                page_texts.append(
                    f"\n## Page {page_number}\n\n{text}\n"
                )

    finally:
        doc.close()

    full_text = "\n".join(page_texts).strip()

    # Whole-document quality check
    if len(full_text) < 1000:
        requires_docling = True
        reasons.append("Insufficient total extracted text")

    # A PDF with many image-only pages may require OCR
    if not full_text:
        requires_docling = True
        reasons.append("No extractable text")

    return full_text, requires_docling, reasons


# ============================================================
# 6. DOCLING FALLBACK
# ============================================================

docling_converter = None


def get_docling_converter():

    global docling_converter

    if docling_converter is not None:
        return docling_converter

    print("\nInitializing Docling...")

    from docling.document_converter import (
        DocumentConverter,
        PdfFormatOption
    )

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_options = PdfPipelineOptions()

    # Do not export picture images
    pipeline_options.generate_picture_images = False

    # Do not generate full page images
    pipeline_options.generate_page_images = False

    # Keep table recognition
    pipeline_options.do_table_structure = True

    # OCR is only used in the Docling fallback
    pipeline_options.do_ocr = ENABLE_OCR

    docling_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )

    return docling_converter


def extract_with_docling(pdf_path):

    converter = get_docling_converter()

    result = converter.convert(pdf_path)

    markdown = result.document.export_to_markdown()

    if not markdown.strip():
        raise RuntimeError("Docling returned empty Markdown")

    return markdown


# ============================================================
# 7. MARKDOWN HEADER
# ============================================================

def create_markdown_header(pdf_path, parser):

    # JSON string is also valid as a quoted YAML scalar
    source_path = json.dumps(str(pdf_path), ensure_ascii=False)
    filename = json.dumps(pdf_path.name, ensure_ascii=False)

    return (
        "---\n"
        f"source_pdf: {source_path}\n"
        f"source_filename: {filename}\n"
        f"parser: {parser}\n"
        "---\n\n"
    )


# ============================================================
# 8. INCREMENTAL CONVERSION
# ============================================================

def is_already_converted(pdf_path, md_file):

    if not SKIP_EXISTING:
        return False

    if not md_file.exists():
        return False

    key = str(pdf_path)
    record = manifest.get(key)

    if not record:
        return False

    stat = pdf_path.stat()

    return (
        record.get("size") == stat.st_size
        and record.get("mtime_ns") == stat.st_mtime_ns
        and record.get("status") == "success"
        and record.get("output") == str(md_file)
    )


# ============================================================
# 9. BATCH PROCESSING
# ============================================================

success = 0
failed = 0
skipped = 0

total_start = time.time()

with FAILURE_LOG.open("w", encoding="utf-8") as flog, \
     TIME_LOG.open("w", encoding="utf-8") as tlog:

    tlog.write("PDF\tParser\tStatus\tSeconds\n")

    for index, pdf in enumerate(pdf_files, 1):

        pdf = pdf.resolve()
        relative_path = pdf.relative_to(PDF_INPUT)

        output_dir = MD_OUTPUT / relative_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        md_file = output_dir / f"{pdf.stem}.md"

        print("\n" + "-" * 65)
        print(f"[{index}/{len(pdf_files)}] {relative_path}")

        if is_already_converted(pdf, md_file):

            skipped += 1

            print("SKIPPED: Already converted and unchanged")
            tlog.write(f"{pdf}\t-\tSKIPPED\t0\n")

            continue

        start = time.time()
        parser = "unknown"

        try:

            # Fast path: PyMuPDF
            text, needs_docling, reasons = extract_with_pymupdf(pdf)

            if ENABLE_DOCLING and needs_docling:

                parser = "Docling"

                print("Using Docling:")
                for reason in reasons:
                    print(f"  - {reason}")

                markdown = extract_with_docling(pdf)

            else:

                parser = "PyMuPDF"
                markdown = text

                if needs_docling and not ENABLE_DOCLING:
                    print(
                        "WARNING: Complex PDF detected, "
                        "but Docling fallback is disabled."
                    )

            header = create_markdown_header(pdf, parser)

            temp_file = md_file.with_suffix(".md.tmp")

            temp_file.write_text(
                header + markdown + "\n",
                encoding="utf-8"
            )

            temp_file.replace(md_file)

            elapsed = time.time() - start

            stat = pdf.stat()

            # Update manifest only after successful output
            manifest[str(pdf)] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "status": "success",
                "parser": parser,
                "output": str(md_file),
                "converted_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            }

            save_manifest()

            success += 1

            print(f"SUCCESS: {parser}")
            print(f"Output: {md_file}")
            print(f"Time: {elapsed:.1f} seconds")

            tlog.write(
                f"{pdf}\t{parser}\tSUCCESS\t{elapsed:.2f}\n"
            )

        except Exception as error:

            elapsed = time.time() - start
            failed += 1

            print(f"FAILED: {pdf}")
            print(f"Error: {error}")

            flog.write(
                f"PDF: {pdf}\n"
                f"Error: {repr(error)}\n"
                f"{traceback.format_exc()}\n"
                + "=" * 65 + "\n"
            )

            tlog.write(
                f"{pdf}\t{parser}\tFAILED\t{elapsed:.2f}\n"
            )

            # Do not add failed PDFs to successful manifest.
            # They will be retried on the next run.


# ============================================================
# 10. SUMMARY
# ============================================================

total_elapsed = time.time() - total_start

print("\n" + "=" * 65)
print("CONVERSION FINISHED")
print("=" * 65)

print(f"Total PDFs : {len(pdf_files)}")
print(f"Successful: {success}")
print(f"Skipped   : {skipped}")
print(f"Failed    : {failed}")

print(f"Total time: {total_elapsed / 60:.2f} minutes")

print(f"\nManifest : {MANIFEST_FILE}")
print(f"Failure  : {FAILURE_LOG}")
print(f"Time log : {TIME_LOG}")

print("=" * 65)
