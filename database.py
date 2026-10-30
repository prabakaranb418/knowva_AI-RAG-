"""PostgreSQL storage: documents, conversations, messages and summaries.

Tables from the first version are kept. New columns and tables are added with
"IF NOT EXISTS", and old chat rows are grouped into conversations on start-up,
so an existing database keeps working.
"""
import json
import os
import uuid
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def _database_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured. Add it to your .env file or deployment secrets.")
    return url


@contextmanager
def get_connection():
    with psycopg.connect(_database_url(), row_factory=dict_row, connect_timeout=8) as conn:
        yield conn


def _iso(value):
    return value.isoformat() if value else None


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id UUID PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                page_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL,
                file_size BIGINT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'PDF',
                location_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id UUID PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                title_auto BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id BIGSERIAL PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                summary_id UUID PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                language TEXT NOT NULL,
                format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Additive migrations for databases created by earlier versions.
        conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_type TEXT NOT NULL DEFAULT 'PDF'")
        conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS location_count INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(conversation_id) ON DELETE CASCADE")
        conn.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'qa'")
        conn.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_visitor_created ON chat_history(visitor_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_history(conversation_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_visitor_created ON documents(visitor_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_visitor_updated ON conversations(visitor_id, updated_at DESC)")
        _adopt_old_chats(conn)


def _adopt_old_chats(conn):
    """Group chat rows saved before conversations existed into one conversation per document."""
    groups = conn.execute("""
        SELECT visitor_id, document_id, MIN(created_at) AS started, MAX(created_at) AS ended,
               (ARRAY_AGG(question ORDER BY created_at))[1] AS first_question
        FROM chat_history WHERE conversation_id IS NULL
        GROUP BY visitor_id, document_id
    """).fetchall()
    for group in groups:
        conversation_id = str(uuid.uuid4())
        title = (group["first_question"] or "Earlier chat").strip()[:60] or "Earlier chat"
        conn.execute("""
            INSERT INTO conversations (conversation_id, visitor_id, document_id, title, title_auto, created_at, updated_at)
            VALUES (%s, %s, %s, %s, FALSE, %s, %s)
        """, (conversation_id, group["visitor_id"], group["document_id"], title, group["started"], group["ended"]))
        conn.execute("""
            UPDATE chat_history SET conversation_id = %s
            WHERE conversation_id IS NULL AND visitor_id = %s AND document_id = %s
        """, (conversation_id, group["visitor_id"], group["document_id"]))


# ------------------------------------------------------------------ documents

def save_document(document_id, visitor_id, filename, page_count, chunk_count, file_size, file_type="PDF", location_count=0):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO documents (document_id, visitor_id, filename, page_count, chunk_count, file_size, file_type, location_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (document_id, visitor_id, filename, page_count, chunk_count, file_size, file_type, location_count))


# ------------------------------------------------------------------ conversations

def create_conversation(visitor_id, document_id, title):
    conversation_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO conversations (conversation_id, visitor_id, document_id, title)
            VALUES (%s, %s, %s, %s)
        """, (conversation_id, visitor_id, document_id, title[:120]))
    return conversation_id


def _conversation_row(row):
    return {
        "conversation_id": str(row["conversation_id"]),
        "document_id": str(row["document_id"]),
        "title": row["title"],
        "filename": row["filename"],
        "file_type": row["file_type"],
        "chunk_count": row["chunk_count"],
        "page_count": row["page_count"],
        "location_count": row["location_count"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


_CONVERSATION_SELECT = """
    SELECT c.conversation_id, c.document_id, c.title, c.created_at, c.updated_at,
           d.filename, d.file_type, d.chunk_count, d.page_count, d.location_count
    FROM conversations c JOIN documents d ON d.document_id = c.document_id
"""


def list_conversations(visitor_id, limit=100):
    with get_connection() as conn:
        rows = conn.execute(
            _CONVERSATION_SELECT + " WHERE c.visitor_id = %s ORDER BY c.updated_at DESC LIMIT %s",
            (visitor_id, limit),
        ).fetchall()
    return [_conversation_row(r) for r in rows]


def get_conversation(conversation_id, visitor_id):
    with get_connection() as conn:
        row = conn.execute(
            _CONVERSATION_SELECT + " WHERE c.conversation_id = %s AND c.visitor_id = %s",
            (conversation_id, visitor_id),
        ).fetchone()
    return _conversation_row(row) if row else None


def rename_conversation(conversation_id, visitor_id, title):
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE conversations SET title = %s, title_auto = FALSE
            WHERE conversation_id = %s AND visitor_id = %s
        """, (title[:120], conversation_id, visitor_id))
        return cursor.rowcount > 0


def delete_conversation(conversation_id, visitor_id):
    """Delete a conversation. If it was the last one using its document, delete the document too.

    Returns None if the conversation was not found, otherwise
    {"orphan_document_id": str | None, "export_paths": [str, ...]}.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT document_id FROM conversations WHERE conversation_id = %s AND visitor_id = %s",
            (conversation_id, visitor_id),
        ).fetchone()
        if not row:
            return None
        document_id = str(row["document_id"])
        conn.execute("DELETE FROM conversations WHERE conversation_id = %s", (conversation_id,))
        remaining = conn.execute(
            "SELECT 1 FROM conversations WHERE document_id = %s LIMIT 1", (document_id,)
        ).fetchone()
        if remaining:
            return {"orphan_document_id": None, "export_paths": []}
        paths = [r["file_path"] for r in conn.execute(
            "SELECT file_path FROM summaries WHERE document_id = %s", (document_id,)
        ).fetchall()]
        conn.execute("DELETE FROM documents WHERE document_id = %s", (document_id,))
        return {"orphan_document_id": document_id, "export_paths": paths}


# ------------------------------------------------------------------ messages

def save_message(conversation_id, visitor_id, document_id, question, answer, sources=None, kind="qa", meta=None):
    with get_connection() as conn:
        row = conn.execute("""
            INSERT INTO chat_history (conversation_id, visitor_id, document_id, question, answer, sources, kind, meta)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
            RETURNING id, created_at
        """, (conversation_id, visitor_id, document_id, question, answer,
              json.dumps(sources or []), kind, json.dumps(meta or {}))).fetchone()
        conn.execute("UPDATE conversations SET updated_at = NOW() WHERE conversation_id = %s", (conversation_id,))
        if kind == "qa":
            # The first question becomes the title, unless the person already renamed the chat.
            conn.execute("""
                UPDATE conversations SET title = %s, title_auto = FALSE
                WHERE conversation_id = %s AND title_auto
            """, (question.strip()[:60] or "New chat", conversation_id))
    return {"id": row["id"], "created_at": _iso(row["created_at"])}


def _json_value(value, default):
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


def get_messages(conversation_id, visitor_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, kind, question, answer, sources, meta, created_at
            FROM chat_history
            WHERE conversation_id = %s AND visitor_id = %s
            ORDER BY created_at, id
        """, (conversation_id, visitor_id)).fetchall()
    return [{
        "id": r["id"],
        "kind": r["kind"],
        "question": r["question"],
        "answer": r["answer"],
        "sources": _json_value(r["sources"], []),
        "meta": _json_value(r["meta"], {}),
        "created_at": _iso(r["created_at"]),
    } for r in rows]


# ------------------------------------------------------------------ summaries

def save_summary(summary_id, visitor_id, document_id, language, fmt, file_path):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO summaries (summary_id, visitor_id, document_id, language, format, file_path)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (summary_id, visitor_id, document_id, language, fmt, file_path))


def get_summary(summary_id, visitor_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT s.summary_id, s.document_id, s.language, s.format, s.file_path, d.filename
            FROM summaries s JOIN documents d ON d.document_id = s.document_id
            WHERE s.summary_id = %s AND s.visitor_id = %s
        """, (summary_id, visitor_id)).fetchone()
    if not row:
        return None
    return {k: (str(v) if k in ("summary_id", "document_id") else v) for k, v in row.items()}


def get_document(document_id, visitor_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT document_id, filename, file_type FROM documents WHERE document_id = %s AND visitor_id = %s",
            (document_id, visitor_id),
        ).fetchone()
    return {"document_id": str(row["document_id"]), "filename": row["filename"], "file_type": row["file_type"]} if row else None


# Kept for older scripts that imported these names.
def save_chat(visitor_id, document_id, question, answer, sources):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO chat_history (visitor_id, document_id, question, answer, sources)
            VALUES (%s, %s, %s, %s, %s::jsonb)
        """, (visitor_id, document_id, question, answer, json.dumps(sources)))
