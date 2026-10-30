"""Writes a summary to PDF, Word (.docx) or plain text.

Hindi, Tamil and other Indian-language text needs a font that contains those
letters. The code looks for one in this order:
  1. the fonts/ folder next to app.py   (for example NotoSansDevanagari-Regular.ttf)
  2. the folder named in PDF_FONT_DIR
  3. the system font folders (Windows has Nirmala.ttf, which covers all of them)
If none is found, PDF export of that language stops with a clear message and
Word or Text can be chosen instead. Word files use "Nirmala UI" and do not need
a font file.
"""
import html
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from extractors import convert_to_pdf

FORMATS = {
    "pdf": {"label": "PDF", "mime": "application/pdf", "extension": ".pdf"},
    "docx": {"label": "Word", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "extension": ".docx"},
    "txt": {"label": "Text", "mime": "text/plain; charset=utf-8", "extension": ".txt"},
}

INDIC = {"devanagari", "tamil", "telugu", "kannada", "malayalam", "bengali", "gujarati"}


class ExportError(RuntimeError):
    """Message is safe to show to the user."""


# ------------------------------------------------------------------ fonts

def _font_dirs():
    dirs = [Path(__file__).parent / "fonts"]
    configured = os.getenv("PDF_FONT_DIR", "").strip()
    if configured:
        dirs.append(Path(configured))
    windir = os.environ.get("WINDIR", r"C:\Windows")
    dirs += [
        Path(windir) / "Fonts",
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/noto"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
    ]
    return dirs


def find_font(script):
    """Return (regular_path, bold_path_or_None) for a script, or (None, None)."""
    names = []
    if script in INDIC:
        names.append(f"NotoSans{script.capitalize()}-Regular.ttf")
    names.append("Nirmala.ttf")
    for folder in _font_dirs():
        for name in names:
            candidate = folder / name
            if candidate.exists():
                bold_name = name.replace("-Regular.ttf", "-Bold.ttf") if "-Regular" in name else "NirmalaB.ttf"
                bold = folder / bold_name
                return str(candidate), (str(bold) if bold.exists() else None)
    return None, None


# ------------------------------------------------------------------ writers

def _meta_lines(result, filename):
    lines = [f"Language: {result['language']}   Created: {datetime.now().strftime('%d %b %Y')}   Source: {filename}"]
    lines.extend(result.get("notes", []))
    return lines


def _write_txt(result, filename, out_path):
    lines = [f"Summary of {filename}", ""]
    lines.extend(_meta_lines(result, filename))
    lines.extend(["", result["text"], ""])
    Path(out_path).write_text("\n".join(lines), encoding="utf-8-sig")


def _write_docx(result, filename, out_path):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    document = Document()
    indic = result["script"] in INDIC or result["script"] == "unknown"

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)

    if indic:
        for style_name in ("Normal", "Title", "Heading 2", "List Bullet"):
            rpr = document.styles[style_name].element.get_or_add_rPr()
            fonts = rpr.get_or_add_rFonts()
            fonts.set(qn("w:cs"), "Nirmala UI")
            fonts.attrib.pop(qn("w:cstheme"), None)
            size = rpr.find(qn("w:sz"))
            if size is not None and rpr.find(qn("w:szCs")) is None:
                size_cs = size.makeelement(qn("w:szCs"), {qn("w:val"): size.get(qn("w:val"))})
                size.addnext(size_cs)
            bold = rpr.find(qn("w:b"))
            if bold is not None and rpr.find(qn("w:bCs")) is None:
                bold.addnext(bold.makeelement(qn("w:bCs"), {}))

    document.core_properties.title = f"Summary of {filename}"
    document.add_paragraph(f"Summary of {filename}", style="Title")
    meta = document.add_paragraph(_meta_lines(result, filename)[0])
    for run in meta.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x5B, 0x67, 0x76)

    for block in result["blocks"]:
        if block["type"] == "heading":
            document.add_paragraph(block["text"], style="Heading 2")
        elif block["type"] == "bullet":
            document.add_paragraph(block["text"], style="List Bullet")
        else:
            document.add_paragraph(block["text"])

    for note in result.get("notes", []):
        paragraph = document.add_paragraph(note)
        for run in paragraph.runs:
            run.italic = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x5B, 0x67, 0x76)
    document.save(str(out_path))


def _write_pdf(result, filename, out_path):
    script = result["script"]
    needs_font = script in INDIC or script == "unknown"
    regular, bold = find_font(script) if needs_font else (None, None)

    if needs_font and not regular:
        # LibreOffice shapes complex scripts itself, so a Word copy converted to PDF can still work.
        if script in INDIC:
            with tempfile.TemporaryDirectory(prefix="knowva_pdf_") as temp:
                docx_path = Path(temp) / "summary.docx"
                _write_docx(result, filename, docx_path)
                converted = convert_to_pdf(docx_path, temp)
                if converted:
                    shutil.move(converted, out_path)
                    return
            raise ExportError(
                f"A PDF in {result['language']} needs a font that contains its letters, and none was found. "
                "Choose Word or Text instead, or add NotoSans fonts to the fonts folder (see README)."
            )

    import fitz  # PyMuPDF

    css = (
        "body{font-family:%s;font-size:11pt;line-height:1.5;color:#1b2430}"
        "h1{font-size:19pt;margin:0 0 4pt}h2{font-size:13.5pt;margin:16pt 0 4pt}"
        "p{margin:0 0 8pt}li{margin:0 0 4pt}.meta{color:#5b6776;font-size:9.5pt}"
    )
    archive = None
    if regular:
        folder = Path(regular).parent
        face = f"@font-face{{font-family:indic;src:url('{Path(regular).name}');}}"
        if bold:
            face += f"@font-face{{font-family:indic;font-weight:bold;src:url('{Path(bold).name}');}}"
        css = face + (css % "indic, sans-serif")
        archive = fitz.Archive(str(folder))
    else:
        css = css % "sans-serif"

    parts = [f"<h1>{html.escape('Summary of ' + filename)}</h1>"]
    parts.append(f"<p class='meta'>{html.escape(_meta_lines(result, filename)[0])}</p>")
    open_list = False
    for block in result["blocks"]:
        if block["type"] != "bullet" and open_list:
            parts.append("</ul>")
            open_list = False
        text = html.escape(block["text"])
        if block["type"] == "heading":
            parts.append(f"<h2>{text}</h2>")
        elif block["type"] == "bullet":
            if not open_list:
                parts.append("<ul>")
                open_list = True
            parts.append(f"<li>{text}</li>")
        else:
            parts.append(f"<p>{text}</p>")
    if open_list:
        parts.append("</ul>")
    for note in result.get("notes", []):
        parts.append(f"<p class='meta'><i>{html.escape(note)}</i></p>")

    story = fitz.Story(html="".join(parts), user_css=css, archive=archive)
    writer = fitz.DocumentWriter(str(out_path))
    media = fitz.paper_rect("a4")
    area = media + (56, 56, -56, -56)
    more = True
    while more:
        device = writer.begin_page(media)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()


def export_summary(result, filename, fmt, out_path):
    """Write the summary and return the path. `fmt` is 'pdf', 'docx' or 'txt'."""
    if fmt not in FORMATS:
        raise ExportError("Choose PDF, Word or Text.")
    if fmt == "txt":
        _write_txt(result, filename, out_path)
    elif fmt == "docx":
        _write_docx(result, filename, out_path)
    else:
        _write_pdf(result, filename, out_path)
    return out_path
