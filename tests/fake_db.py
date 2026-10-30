"""In-memory stand-in for database.py, used only by the tests.

It has the same function names and return shapes as the real module, so the
Flask routes can be tested without a PostgreSQL server. It is not used by the app.
"""
import itertools
import uuid
from datetime import datetime, timedelta, timezone

_clock = itertools.count()
documents, conversations, messages, summaries = {}, {}, [], {}


def _now():
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=next(_clock))


def reset():
    documents.clear(); conversations.clear(); messages.clear(); summaries.clear()


def init_db():
    pass


def save_document(document_id, visitor_id, filename, page_count, chunk_count, file_size, file_type="PDF", location_count=0):
    documents[document_id] = dict(document_id=document_id, visitor_id=visitor_id, filename=filename, page_count=page_count,
                                  chunk_count=chunk_count, file_type=file_type, location_count=location_count)


def create_conversation(visitor_id, document_id, title):
    cid = str(uuid.uuid4())
    now = _now()
    conversations[cid] = dict(conversation_id=cid, visitor_id=visitor_id, document_id=document_id, title=title[:120],
                              title_auto=True, created_at=now, updated_at=now)
    return cid


def _view(conv):
    doc = documents[conv["document_id"]]
    return {
        "conversation_id": conv["conversation_id"], "document_id": conv["document_id"], "title": conv["title"],
        "filename": doc["filename"], "file_type": doc["file_type"], "chunk_count": doc["chunk_count"],
        "page_count": doc["page_count"], "location_count": doc["location_count"],
        "created_at": conv["created_at"].isoformat(), "updated_at": conv["updated_at"].isoformat(),
    }


def list_conversations(visitor_id, limit=100):
    mine = [c for c in conversations.values() if c["visitor_id"] == visitor_id]
    return [_view(c) for c in sorted(mine, key=lambda c: c["updated_at"], reverse=True)[:limit]]


def get_conversation(conversation_id, visitor_id):
    conv = conversations.get(conversation_id)
    return _view(conv) if conv and conv["visitor_id"] == visitor_id else None


def rename_conversation(conversation_id, visitor_id, title):
    conv = conversations.get(conversation_id)
    if not conv or conv["visitor_id"] != visitor_id:
        return False
    conv["title"], conv["title_auto"] = title[:120], False
    return True


def delete_conversation(conversation_id, visitor_id):
    conv = conversations.get(conversation_id)
    if not conv or conv["visitor_id"] != visitor_id:
        return None
    del conversations[conversation_id]
    messages[:] = [m for m in messages if m["conversation_id"] != conversation_id]
    document_id = conv["document_id"]
    if any(c["document_id"] == document_id for c in conversations.values()):
        return {"orphan_document_id": None, "export_paths": []}
    paths = [s["file_path"] for s in summaries.values() if s["document_id"] == document_id]
    for sid in [k for k, s in summaries.items() if s["document_id"] == document_id]:
        del summaries[sid]
    documents.pop(document_id, None)
    return {"orphan_document_id": document_id, "export_paths": paths}


def save_message(conversation_id, visitor_id, document_id, question, answer, sources=None, kind="qa", meta=None):
    now = _now()
    row = dict(id=len(messages) + 1, conversation_id=conversation_id, visitor_id=visitor_id, kind=kind, question=question,
               answer=answer, sources=sources or [], meta=meta or {}, created_at=now)
    messages.append(row)
    conv = conversations[conversation_id]
    conv["updated_at"] = now
    if kind == "qa" and conv["title_auto"]:
        conv["title"], conv["title_auto"] = question.strip()[:60], False
    return {"id": row["id"], "created_at": now.isoformat()}


def get_messages(conversation_id, visitor_id):
    return [dict(m, created_at=m["created_at"].isoformat()) for m in messages
            if m["conversation_id"] == conversation_id and m["visitor_id"] == visitor_id]


def save_summary(summary_id, visitor_id, document_id, language, fmt, file_path):
    summaries[summary_id] = dict(summary_id=summary_id, visitor_id=visitor_id, document_id=document_id,
                                 language=language, format=fmt, file_path=file_path)


def get_summary(summary_id, visitor_id):
    row = summaries.get(summary_id)
    if not row or row["visitor_id"] != visitor_id:
        return None
    return dict(row, filename=documents[row["document_id"]]["filename"])


def get_document(document_id, visitor_id):
    doc = documents.get(document_id)
    if not doc or doc["visitor_id"] != visitor_id:
        return None
    return {"document_id": doc["document_id"], "filename": doc["filename"], "file_type": doc["file_type"]}
