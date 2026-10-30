import pytest
from docx import Document

import exporter

BLOCKS = [
    {"type": "paragraph", "text": "The overview paragraph. [p.1 ¶2]"},
    {"type": "heading", "text": "Key points"},
    {"type": "bullet", "text": "First point [p.2 ¶1]"},
    {"type": "bullet", "text": "Second point"},
]


def result(language="English", script="latin", notes=("A note.",), blocks=BLOCKS):
    text = "\n".join(b["text"] for b in blocks)
    return {"language": language, "script": script, "blocks": blocks, "text": text, "notes": list(notes), "parts": 1}


def test_text_export(tmp_path):
    out = tmp_path / "s.txt"
    exporter.export_summary(result(), "report.pdf", "txt", out)
    content = out.read_text(encoding="utf-8-sig")
    assert "Summary of report.pdf" in content
    assert "The overview paragraph. [p.1 ¶2]" in content
    assert "A note." in content


def test_word_export_keeps_structure(tmp_path):
    out = tmp_path / "s.docx"
    exporter.export_summary(result(), "report.pdf", "docx", out)
    document = Document(str(out))
    styles = {p.text: p.style.name for p in document.paragraphs}
    assert styles["Summary of report.pdf"] == "Title"
    assert styles["Key points"] == "Heading 2"
    assert styles["First point [p.2 ¶1]"] == "List Bullet"


def test_word_export_sets_a_complex_script_font_for_hindi(tmp_path):
    out = tmp_path / "hi.docx"
    hindi = [{"type": "paragraph", "text": "यह एक सारांश है। [p.1 ¶1]"}]
    exporter.export_summary(result("Hindi", "devanagari", blocks=hindi), "रिपोर्ट.docx", "docx", out)
    document = Document(str(out))
    assert any("यह एक सारांश है" in p.text for p in document.paragraphs)
    normal_fonts = document.styles["Normal"].element.rPr.rFonts
    assert normal_fonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cs") == "Nirmala UI"


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(exporter.ExportError):
        exporter.export_summary(result(), "a.pdf", "rtf", tmp_path / "x")


def test_font_search_uses_the_configured_folder(tmp_path, monkeypatch):
    (tmp_path / "NotoSansTamil-Regular.ttf").write_bytes(b"x")
    (tmp_path / "NotoSansTamil-Bold.ttf").write_bytes(b"x")
    monkeypatch.setenv("PDF_FONT_DIR", str(tmp_path))
    regular, bold = exporter.find_font("tamil")
    assert regular.endswith("NotoSansTamil-Regular.ttf")
    assert bold.endswith("NotoSansTamil-Bold.ttf")


def test_pdf_export_for_english(tmp_path):
    pytest.importorskip("fitz")
    out = tmp_path / "s.pdf"
    exporter.export_summary(result(), "report.pdf", "pdf", out)
    assert out.read_bytes().startswith(b"%PDF")
