"""Turns an uploaded file into "units" that remember where they came from.

Location rules (what the reader sees as a citation):
  PDF      Page N, Paragraph M        (paragraph = text block on that page)
  Word     Page N, Paragraph M        (page from the breaks Word saved, or from a
                                       LibreOffice PDF conversion; see _read_docx)
  TXT, MD  Paragraph M                (paragraphs are separated by blank lines)
  Others   Slide / Sheet+row / Row / JSON path / HTML element, as before

Locations always come from this code, never from the language model.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path


@dataclass
class Unit:
    text: str
    kind: str                      # "paragraph", "table row", "slide", ...
    page: int | None = None
    para: int | None = None        # paragraph number (restarts on every page when pages exist)
    label: str | None = None       # explicit label for non-paragraph units


@dataclass
class ReadResult:
    units: list
    page_count: int = 0            # real pages, 0 when unknown
    location_count: int = 0
    page_source: str = "none"      # "pdf" | "word_breaks" | "converted_pdf" | "none"
    render_pdf: str | None = None  # PDF file that can be rendered for the viewer
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------- PDF

def blocks_to_paragraphs(blocks):
    """Convert PyMuPDF text blocks into paragraph strings.

    Skips image blocks, empty blocks and a bare page number such as "12".
    """
    paragraphs = []
    for block in blocks:
        if len(block) >= 7 and block[6] != 0:      # 0 = text block, 1 = image block
            continue
        text = " ".join(str(block[4]).split())
        if not text:
            continue
        if text.isdigit() and len(text) <= 4:
            continue
        paragraphs.append(text)
    return paragraphs


def _read_pdf(path):
    import fitz  # PyMuPDF

    units = []
    with fitz.open(path) as document:
        if document.is_encrypted:
            raise ValueError("This PDF is password-protected. Please upload an unlocked PDF.")
        count = len(document)
        for page_number, page in enumerate(document, start=1):
            blocks = page.get_text("blocks", sort=True)
            for para_number, text in enumerate(blocks_to_paragraphs(blocks), start=1):
                units.append(Unit(text, "paragraph", page=page_number, para=para_number))
    return ReadResult(units, page_count=count, location_count=count, page_source="pdf", render_pdf=str(path))


# ---------------------------------------------------------------- Word

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_T, _BR, _LRPB, _PBB, _TYPE, _VAL = (
    _W + "t", _W + "br", _W + "lastRenderedPageBreak", _W + "pageBreakBefore", _W + "type", _W + "val",
)


def _page_break_mode(body):
    """Decide where page numbers can come from.

    "rendered": Word saved lastRenderedPageBreak marks, which record where Word
                itself broke the pages. Most reliable.
    "explicit": only hard page breaks the author inserted.
    None:       no page information in the file.
    """
    if next(body.iter(_LRPB), None) is not None:
        return "rendered"
    for element in body.iter():
        if element.tag == _BR and element.get(_TYPE) == "page":
            return "explicit"
        if element.tag == _PBB and element.get(_VAL) not in ("0", "false"):
            return "explicit"
    return None


def _scan_breaks(element, mode):
    """Walk an element in document order.

    Returns (breaks_before_first_text, total_breaks): the first number says
    whether the text starts on a later page than the element's position.
    """
    breaks = 0
    before_text = None
    for node in element.iter():
        tag = node.tag
        if tag == _T:
            if node.text and node.text.strip() and before_text is None:
                before_text = breaks
        elif mode == "rendered":
            if tag == _LRPB:
                breaks += 1
        elif mode == "explicit":
            if tag == _BR and node.get(_TYPE) == "page":
                breaks += 1
            elif tag == _PBB and node.get(_VAL) not in ("0", "false"):
                breaks += 1
    if before_text is None:
        before_text = breaks
    return before_text, breaks


def _find_soffice():
    configured = os.getenv("SOFFICE_PATH", "").strip()
    if configured and os.path.exists(configured):
        return configured
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_to_pdf(path, out_dir):
    """Convert an Office file to PDF with LibreOffice. Returns the PDF path or None."""
    executable = _find_soffice()
    if not executable:
        return None
    profile = tempfile.mkdtemp(prefix="knowva_lo_")
    try:
        subprocess.run(
            [executable, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
             "--convert-to", "pdf", "--outdir", str(out_dir), str(path)],
            check=True, capture_output=True, timeout=180,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    produced = Path(out_dir) / (Path(path).stem + ".pdf")
    return str(produced) if produced.exists() else None


def _read_docx(path, work_dir=None):
    from docx import Document as WordDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = WordDocument(path)
    body = document.element.body
    mode = _page_break_mode(body)

    if mode is None and work_dir is not None:
        # No page information inside the file. A LibreOffice PDF gives real pages.
        pdf_path = convert_to_pdf(path, work_dir)
        if pdf_path:
            try:
                converted = _read_pdf(pdf_path)
            except ImportError:
                converted = None
            if converted and converted.units:
                converted.page_source = "converted_pdf"
                converted.notes.append("Pages come from a PDF copy made with LibreOffice and may differ slightly from Word.")
                return converted

    units = []
    page = 1
    para_number = 0
    table_number = 0
    qn_tbl, qn_p = _W + "tbl", _W + "p"

    for child in body.iterchildren():
        if child.tag == qn_p:
            before, total = _scan_breaks(child, mode)
            text = Paragraph(child, document).text.strip()
            if mode:
                if before:
                    para_number = 0              # the text starts on a new page
                if text:
                    para_number += 1
                    units.append(Unit(text, "paragraph", page=page + before, para=para_number))
                page += total
                if total > before:
                    para_number = 0              # a break inside the paragraph: next one starts a new page
            elif text:
                para_number += 1
                units.append(Unit(text, "paragraph", page=None, para=para_number))
        elif child.tag == qn_tbl:
            table_number += 1
            table = Table(child, document)
            for row_number, row in enumerate(table.rows, start=1):
                before, total = _scan_breaks(row._tr, mode)
                values = []
                for cell in row.cells:
                    cell_text = cell.text.strip().replace("\n", " / ")
                    if cell_text and cell_text not in values:
                        values.append(cell_text)
                text = " | ".join(values)
                if text:
                    where = f"Page {page + before}, " if mode else ""
                    units.append(Unit(text, "table row", page=(page + before) if mode else None,
                                      label=f"{where}Table {table_number}, row {row_number}"))
                if mode and total:
                    page += total
                    para_number = 0

    notes = []
    if mode == "rendered":
        page_source = "word_breaks"
    elif mode == "explicit":
        page_source = "word_breaks"
        notes.append("Pages are counted from page breaks in the file; text that flows onto a new page by itself is not counted.")
    else:
        page_source = "none"
        notes.append("This Word file has no page information, so locations use paragraph numbers only. Install LibreOffice to get page numbers.")
    page_count = page if mode else 0
    return ReadResult(units, page_count=page_count, location_count=len(units), page_source=page_source, notes=notes)


# ---------------------------------------------------------------- Text

def split_paragraphs(text):
    """Split plain text into paragraphs on blank lines.

    If the file has no blank lines at all, every non-empty line becomes a paragraph.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) == 1 and "\n" in text.strip():
        paragraphs = [" ".join(line.split()) for line in text.split("\n") if line.strip()]
    return paragraphs


def _read_text_file(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    units = [Unit(p, "paragraph", page=None, para=i) for i, p in enumerate(split_paragraphs(text), start=1)]
    return ReadResult(units, page_count=0, location_count=len(units), page_source="none")


# ---------------------------------------------------------------- Other formats (unchanged behaviour)

def _read_spreadsheet(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    units = []
    sheets = set()
    try:
        for sheet in workbook.worksheets:
            for row_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if values:
                    sheets.add(sheet.title)
                    units.append(Unit(" | ".join(values), "spreadsheet row", label=f"Sheet '{sheet.title}', row {row_no}"))
    finally:
        workbook.close()
    return ReadResult(units, location_count=len(sheets))


def _read_pptx(path):
    from pptx import Presentation

    presentation = Presentation(path)
    units = []
    for slide_no, slide in enumerate(presentation.slides, start=1):
        pieces = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                pieces.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    pieces.append(" | ".join(cell.text.strip() for cell in row.cells))
        text = "\n".join(pieces).strip()
        if text:
            units.append(Unit(text, "slide", label=f"Slide {slide_no}"))
    return ReadResult(units, location_count=len(presentation.slides))


def _read_csv(path):
    units = []
    with open(path, "r", encoding="utf-8-sig", newline="", errors="replace") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        for row_no, row in enumerate(csv.reader(handle, dialect), start=1):
            values = [cell.strip() for cell in row if cell.strip()]
            if values:
                units.append(Unit(" | ".join(values), "row", label=f"Row {row_no}"))
    return ReadResult(units, location_count=len(units))


def _read_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    units = []

    def walk(value, key_path="$", depth=0):
        if depth > 20:
            units.append(Unit(json.dumps(value, ensure_ascii=False, default=str), "JSON path", label=f"JSON path {key_path}"))
        elif isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{key_path}.{key}", depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{key_path}[{index}]", depth + 1)
        elif value is not None:
            units.append(Unit(f"{key_path}: {value}", "JSON path", label=f"JSON path {key_path}"))

    walk(data)
    return ReadResult(units, location_count=len(units))


def _read_html(path):
    from bs4 import BeautifulSoup

    html = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    units = []
    for index, element in enumerate(soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "blockquote"]), start=1):
        text = element.get_text(" ", strip=True)
        if text:
            units.append(Unit(text, "HTML element", label=f"HTML {element.name.upper()} element {index}"))
    if not units:
        text = soup.get_text(" ", strip=True)
        if text:
            units.append(Unit(unescape(text), "document", label="HTML document"))
    return ReadResult(units, location_count=len(units))


SUPPORTED = (".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".txt", ".md", ".csv", ".json", ".html", ".htm")

_SIMPLE = {
    ".pdf": _read_pdf, ".xlsx": _read_spreadsheet, ".xlsm": _read_spreadsheet, ".pptx": _read_pptx,
    ".txt": _read_text_file, ".md": _read_text_file, ".csv": _read_csv, ".json": _read_json,
    ".html": _read_html, ".htm": _read_html,
}


def read_file(path, extension, work_dir=None):
    """Read `path` and return a ReadResult. `work_dir` is where a converted PDF may be written."""
    extension = extension.lower()
    if extension == ".docx":
        return _read_docx(path, work_dir=work_dir)
    reader = _SIMPLE.get(extension)
    if not reader:
        raise ValueError(f"Unsupported file type. Supported formats: {', '.join(SUPPORTED)}")
    return reader(path)
