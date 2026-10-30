from rag_engine import split_text


def test_split_text_empty():
    assert split_text("") == []
    assert split_text("   ") == []


def test_split_text_preserves_content():
    text = ("A sentence about document retrieval. " * 100).strip()
    chunks = split_text(text, max_chars=180, overlap=20)
    assert chunks
    assert all(chunk.strip() for chunk in chunks)
    assert any("document retrieval" in chunk for chunk in chunks)
