import os
import re
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# Folders and settings are set before the app is imported.
_WORK = tempfile.mkdtemp(prefix="knowva_tests_")
os.environ.update({
    "UPLOAD_FOLDER": os.path.join(_WORK, "uploads"),
    "INDEX_FOLDER": os.path.join(_WORK, "indexes"),
    "EXPORT_FOLDER": os.path.join(_WORK, "exports"),
    "FLASK_SECRET_KEY": "test-secret",
    "GEMINI_API_KEY": "test-key-not-real",
})

import fake_db  # noqa: E402

sys.modules["database"] = fake_db  # the app imports "database"; tests use the in-memory version


def fake_embed(texts):
    """Deterministic bag-of-words vectors, so retrieval works without downloading a model."""
    vectors = []
    for text in texts:
        vector = np.zeros(128, dtype="float32")
        for word in re.findall(r"\w+", text.lower()):
            vector[zlib.crc32(word.encode()) % 128] += 1
        norm = np.linalg.norm(vector)
        vectors.append(vector / norm if norm else vector)
    return np.array(vectors, dtype="float32")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    import rag_engine

    fake_db.reset()
    rag_engine._records.clear()
    monkeypatch.setattr(rag_engine, "embed_texts", fake_embed)


@pytest.fixture
def client():
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
