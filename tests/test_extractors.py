from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

import extractors
from extractors import Unit, blocks_to_paragraphs, read_file, split_paragraphs
from rag_engine import make_chunks

LONG = "This sentence is here to make the paragraph long enough to stand on its own as a chunk. " * 3


def test_text_paragraphs_split_on_blank_lines(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("First paragraph.\n\nSecond paragraph\nwraps here.\n\n\nThird.", encoding="utf-8")
    result = read_file(path, ".txt")
    assert [u.text for u in result.units] == ["First paragraph.", "Second paragraph wraps here.", "Third."]
    assert [u.para for u in result.units] == [1, 2, 3]
    assert all(u.page is None for u in result.units)


def test_text_without_blank_lines_uses_each_line():
    assert split_paragraphs("one\ntwo\nthree") == ["one", "two", "three"]


def test_pdf_blocks_skip_images_and_bare_page_numbers():
    blocks = [
        (0, 0, 1, 1, "Intro text\nwraps", 0, 0),
        (0, 0, 1, 1, "<image>", 1, 1),
        (0, 0, 1, 1, "12", 2, 0),
        (0, 0, 1, 1, "   ", 3, 0),
        (0, 0, 1, 1, "Second block", 4, 0),
    ]
    assert blocks_to_paragraphs(blocks) == ["Intro text wraps", "Second block"]


def _docx_with_page_breaks(path):
    document = Document()
    document.add_paragraph("Page one, paragraph one. " + LONG)
    document.add_paragraph("Page one, paragraph two. " + LONG)
    document.add_page_break()
    document.add_paragraph("Page two, paragraph one. " + LONG)
    document.add_page_break()
    document.add_paragraph("Page three, paragraph one. " + LONG)
    document.add_paragraph("Page three, paragraph two. " + LONG)
    document.save(path)


def test_word_explicit_page_breaks_give_page_and_paragraph(tmp_path):
    path = tmp_path / "a.docx"
    _docx_with_page_breaks(path)
    result = extractors._read_docx(str(path))
    where = {u.text.split(".")[0]: (u.page, u.para) for u in result.units if u.text.startswith("Page ")}
    assert where["Page one, paragraph one"] == (1, 1)
    assert where["Page one, paragraph two"] == (1, 2)
    assert where["Page two, paragraph one"] == (2, 1)
    assert where["Page three, paragraph one"] == (3, 1)
    assert where["Page three, paragraph two"] == (3, 2)
    assert result.page_count == 3
    assert result.page_source == "word_breaks"


def test_word_rendered_breaks_are_used_when_present(tmp_path):
    """Word writes lastRenderedPageBreak where its own layout starts a new page."""
    path = tmp_path / "r.docx"
    document = Document()
    document.add_paragraph("Alpha " + LONG)
    second = document.add_paragraph("Beta " + LONG)
    document.add_paragraph("Gamma " + LONG)
    run = second.runs[0]._r
    marker = OxmlElement("w:lastRenderedPageBreak")
    run.insert(0, marker)
    document.save(path)

    result = extractors._read_docx(str(path))
    where = {u.text.split(" ")[0]: (u.page, u.para) for u in result.units}
    assert where["Alpha"] == (1, 1)
    assert where["Beta"] == (2, 1)       # starts a new page, numbering restarts
    assert where["Gamma"] == (2, 2)
    assert result.page_count == 2


def test_word_without_any_page_information_uses_paragraph_numbers(tmp_path):
    path = tmp_path / "n.docx"
    document = Document()
    document.add_paragraph("One " + LONG)
    document.add_paragraph("Two " + LONG)
    document.save(path)
    result = extractors._read_docx(str(path))   # no work_dir: no LibreOffice conversion
    assert [(u.page, u.para) for u in result.units] == [(None, 1), (None, 2)]
    assert result.page_source == "none"
    assert result.notes


def test_word_table_rows_get_page_and_row_labels(tmp_path):
    path = tmp_path / "t.docx"
    document = Document()
    document.add_paragraph("Before the table. " + LONG)
    document.add_page_break()
    table = document.add_table(rows=2, cols=2)
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            cell.text = f"cell{r}{c}"
    document.save(path)
    result = extractors._read_docx(str(path))
    rows = [u for u in result.units if u.kind == "table row"]
    assert rows[0].label == "Page 2, Table 1, row 1"
    assert rows[1].label == "Page 2, Table 1, row 2"


def test_exact_paragraph_citation_and_small_paragraph_merging():
    units = [
        Unit("Heading", "paragraph", page=1, para=1),
        Unit(LONG, "paragraph", page=1, para=2),
        Unit(LONG + "second", "paragraph", page=1, para=3),
        Unit("Tiny note", "paragraph", page=2, para=1),
    ]
    chunks = make_chunks(units)
    # The heading is short, so it joins the long paragraph that follows it.
    assert chunks[0].location_label == "Page 1, Paragraphs 1–2"
    # A long paragraph stands alone, so its citation is one exact paragraph.
    assert chunks[1].location_label == "Page 1, Paragraph 3"
    assert chunks[1].short_label == "p.1 ¶3"
    # Merging never crosses a page.
    assert chunks[2].location_label == "Page 2, Paragraph 1"


def test_other_formats_keep_their_own_labels(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    chunks = make_chunks(read_file(path, ".csv").units)
    assert chunks[0].location_label == "Row 1"
    assert chunks[0].page is None
