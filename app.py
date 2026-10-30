import logging
import os
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, Response, jsonify, render_template, request, send_file, session  # noqa: E402
from werkzeug.exceptions import RequestEntityTooLarge  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

import database as db  # noqa: E402
import exporter  # noqa: E402
import rag_engine  # noqa: E402
import summarizer  # noqa: E402
from extractors import SUPPORTED  # noqa: E402
from languages import LANGUAGES, find_language  # noqa: E402
from llm import LLMError  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "development-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
app.config["EXPORT_FOLDER"] = os.getenv("EXPORT_FOLDER", "exports")
app.config["ALLOWED_EXTENSIONS"] = {ext.lstrip(".") for ext in SUPPORTED}
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=int(os.getenv("SESSION_DAYS", "180")))

if app.secret_key == "development-only-change-me":
    logger.warning("FLASK_SECRET_KEY is not set. Set a long random value before deploying.")

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["EXPORT_FOLDER"], exist_ok=True)

try:
    db.init_db()
except Exception:
    # The page still opens while the database is being set up; database routes report the problem.
    logger.exception("Database initialization failed. Check DATABASE_URL and database availability.")


# ------------------------------------------------------------------ helpers

def fail(message, status):
    return jsonify({"error": message}), status


def api(handler):
    """Turn exceptions into clear JSON errors without leaking internals."""
    @wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except exporter.ExportError as exc:
            return fail(str(exc), 422)
        except ValueError as exc:
            return fail(str(exc), 400)
        except (LLMError, RuntimeError) as exc:
            return fail(str(exc), 503)
        except Exception:
            logger.exception("Request failed: %s %s", request.method, request.path)
            return fail("Something went wrong. Check the server log, the model settings and the database connection.", 500)
    return wrapper


@app.before_request
def ensure_visitor():
    if "visitor_id" not in session:
        session["visitor_id"] = str(uuid.uuid4())
    session.permanent = True


def visitor():
    return session["visitor_id"]


def parse_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        return None


def public_conversation(conv):
    return {
        "id": conv["conversation_id"],
        "document_id": conv["document_id"],
        "title": conv["title"],
        "filename": conv["filename"],
        "file_type": conv["file_type"],
        "chunk_count": conv["chunk_count"],
        "page_count": conv["page_count"],
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
    }


def own_conversation(conversation_id):
    """Return the conversation if it belongs to this visitor, else None."""
    cid = parse_uuid(conversation_id)
    return db.get_conversation(cid, visitor()) if cid else None


def open_index(conv):
    return rag_engine.ensure_index(conv["document_id"], rag_engine.upload_path(conv["document_id"]), conv["filename"])


def message_payload(row):
    return {
        "id": row["id"], "kind": row["kind"], "question": row["question"], "answer": row["answer"],
        "sources": row["sources"], "meta": row["meta"], "created_at": row["created_at"],
    }


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


# ------------------------------------------------------------------ pages and config

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "Knowva"})


@app.get("/api/config")
def config():
    return jsonify({
        "languages": LANGUAGES,
        "formats": [{"id": key, "label": value["label"]} for key, value in exporter.FORMATS.items()],
        "extensions": sorted(SUPPORTED),
        "max_upload_mb": app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
    })


# ------------------------------------------------------------------ upload

@app.post("/api/upload")
@api
def upload_document():
    file = request.files.get("file")
    if not file or not file.filename:
        return fail("Choose a document to upload.", 400)
    if not allowed_file(file.filename):
        return fail("Unsupported file type. Upload PDF, DOCX, XLSX, XLSM, PPTX, TXT, MD, CSV, JSON, HTML, or HTM.", 400)

    safe_name = secure_filename(file.filename) or "document" + Path(file.filename).suffix.lower()
    extension = os.path.splitext(safe_name)[1].lower()
    doc_id = str(uuid.uuid4())
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{doc_id}{extension}")

    try:
        file.save(file_path)
        info = rag_engine.process_document(file_path, doc_id, safe_name)
        db.save_document(
            document_id=doc_id,
            visitor_id=visitor(),
            filename=safe_name,
            page_count=info["page_count"],
            chunk_count=info["chunk_count"],
            file_size=os.path.getsize(file_path),
            file_type=info["file_type"],
            location_count=info["location_count"],
        )
        conversation_id = db.create_conversation(visitor(), doc_id, safe_name)
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        rag_engine.delete_document_index(doc_id)
        if isinstance(exc, ValueError):
            raise
        logger.exception("Document upload/processing failed")
        return fail("We could not process this document. It may be damaged, encrypted, empty, or use unsupported content.", 500)

    conv = db.get_conversation(conversation_id, visitor())
    return jsonify({"conversation": public_conversation(conv), "document": info})


# ------------------------------------------------------------------ conversations

@app.get("/api/conversations")
@api
def conversations():
    return jsonify({"conversations": [public_conversation(c) for c in db.list_conversations(visitor())]})


@app.get("/api/conversations/<conversation_id>")
@api
def open_conversation(conversation_id):
    conv = own_conversation(conversation_id)
    if not conv:
        return fail("That conversation was not found.", 404)
    document, index_error = None, None
    try:
        document = rag_engine.describe(open_index(conv))
    except RuntimeError as exc:
        index_error = str(exc)
    messages = [message_payload(m) for m in db.get_messages(conv["conversation_id"], visitor())]
    return jsonify({"conversation": public_conversation(conv), "document": document, "index_error": index_error, "messages": messages})


@app.patch("/api/conversations/<conversation_id>")
@api
def rename_conversation(conversation_id):
    cid = parse_uuid(conversation_id)
    title = ((request.get_json(silent=True) or {}).get("title") or "").strip()
    if not title:
        return fail("Enter a name for this conversation.", 400)
    if not cid or not db.rename_conversation(cid, visitor(), title):
        return fail("That conversation was not found.", 404)
    return jsonify({"title": title[:120]})


@app.delete("/api/conversations/<conversation_id>")
@api
def delete_conversation(conversation_id):
    cid = parse_uuid(conversation_id)
    outcome = db.delete_conversation(cid, visitor()) if cid else None
    if outcome is None:
        return fail("That conversation was not found.", 404)
    document_id = outcome["orphan_document_id"]
    if document_id:
        upload = rag_engine.upload_path(document_id)
        if upload and os.path.exists(upload):
            os.remove(upload)
        rag_engine.delete_document_index(document_id)
        for path in outcome["export_paths"]:
            if path and os.path.exists(path):
                os.remove(path)
    return jsonify({"deleted": True})


# ------------------------------------------------------------------ questions

@app.post("/api/ask")
@api
def ask():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    conv = own_conversation(payload.get("conversation_id"))
    if not conv:
        return fail("Upload a document or open a conversation first.", 400)
    if not question:
        return fail("Enter a question first.", 400)
    if len(question) > 2000:
        return fail("Questions must be 2,000 characters or fewer.", 400)

    open_index(conv)
    result = rag_engine.answer_question(conv["document_id"], question)
    saved = db.save_message(conv["conversation_id"], visitor(), conv["document_id"], question, result["answer"], result["sources"])
    return jsonify({
        "id": saved["id"], "kind": "qa", "question": question, "answer": result["answer"],
        "sources": result["sources"], "meta": {"cited": result["cited"]}, "created_at": saved["created_at"],
    })


# ------------------------------------------------------------------ summaries

@app.post("/api/summarize")
@api
def summarize_document():
    payload = request.get_json(silent=True) or {}
    conv = own_conversation(payload.get("conversation_id"))
    if not conv:
        return fail("Open a conversation first.", 400)
    fmt = (payload.get("format") or "").lower()
    if fmt not in exporter.FORMATS:
        return fail("Choose PDF, Word or Text.", 400)
    language = find_language(payload.get("language") or "English")

    open_index(conv)
    result = summarizer.summarize(rag_engine.all_chunks(conv["document_id"]), conv["filename"], language["name"])

    summary_id = str(uuid.uuid4())
    out_path = Path(app.config["EXPORT_FOLDER"]) / f"{summary_id}{exporter.FORMATS[fmt]['extension']}"
    export_error = None
    try:
        exporter.export_summary(result, conv["filename"], fmt, out_path)
        db.save_summary(summary_id, visitor(), conv["document_id"], language["name"], fmt, str(out_path))
    except exporter.ExportError as exc:
        # The summary text is still useful, so keep it and say why the file is missing.
        export_error = str(exc)
        summary_id = None

    meta = {
        "summary_id": summary_id, "format": fmt, "format_label": exporter.FORMATS[fmt]["label"],
        "language": language["name"], "notes": result["notes"], "export_error": export_error,
        "blocks": result["blocks"],
    }
    question = f"Summarize this document · {language['name']} · {exporter.FORMATS[fmt]['label']}"
    saved = db.save_message(conv["conversation_id"], visitor(), conv["document_id"], question, result["text"], [], kind="summary", meta=meta)
    return jsonify({
        "id": saved["id"], "kind": "summary", "question": question, "answer": result["text"],
        "sources": [], "meta": meta, "created_at": saved["created_at"],
    })


@app.get("/api/summaries/<summary_id>/download")
@api
def download_summary(summary_id):
    sid = parse_uuid(summary_id)
    row = db.get_summary(sid, visitor()) if sid else None
    if not row or not os.path.exists(row["file_path"]):
        return fail("That summary file is no longer available. Create it again.", 404)
    fmt = exporter.FORMATS.get(row["format"], exporter.FORMATS["txt"])
    stem = secure_filename(Path(row["filename"]).stem) or "document"
    name = f"{stem}-summary-{secure_filename(row['language']) or 'summary'}{fmt['extension']}"
    return send_file(row["file_path"], mimetype=fmt["mime"], as_attachment=True, download_name=name)


# ------------------------------------------------------------------ viewer

def own_document(document_id):
    did = parse_uuid(document_id)
    return db.get_document(did, visitor()) if did else None


@app.get("/api/documents/<document_id>/page/<int:page>.png")
@api
def document_page(document_id, page):
    doc = own_document(document_id)
    if not doc:
        return fail("That document was not found.", 404)
    rag_engine.ensure_index(doc["document_id"], rag_engine.upload_path(doc["document_id"]), doc["filename"])
    chunk = request.args.get("chunk", type=int)
    image = rag_engine.render_page(doc["document_id"], page, chunk_id=chunk)
    return Response(image, mimetype="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/documents/<document_id>/context")
@api
def document_context(document_id):
    doc = own_document(document_id)
    if not doc:
        return fail("That document was not found.", 404)
    chunk = request.args.get("chunk", type=int)
    if chunk is None:
        return fail("Say which passage to show.", 400)
    rag_engine.ensure_index(doc["document_id"], rag_engine.upload_path(doc["document_id"]), doc["filename"])
    return jsonify(rag_engine.get_context(doc["document_id"], chunk))


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    return fail(f"File too large. Maximum upload size is {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB.", 413)


if __name__ == "__main__":
    # For production use a WSGI server such as gunicorn (see Procfile).
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
