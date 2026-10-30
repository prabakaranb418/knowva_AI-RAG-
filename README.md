# Knowva

Ask questions about a document and see the page and paragraph each answer came from.

Flask backend, plain HTML/CSS/JavaScript frontend, Gemini for answers, sentence-transformers + FAISS for retrieval, PostgreSQL for documents and chat history.

## What it does

- **Exact locations.** Every answer carries markers such as `p.4 ¶2`. Click one to open the source.
  - PDF: page and paragraph (a paragraph is a text block on that page).
  - Word: page and paragraph. Pages come from the page breaks Word saved in the file. If the file has none, LibreOffice (if installed) makes a PDF copy to get pages. If neither works, you get paragraph numbers only, and the app says so.
  - Text and Markdown: paragraph numbers (paragraphs are separated by blank lines).
  - Excel, PowerPoint, CSV, JSON, HTML: sheet and row, slide, row, JSON path, HTML element.
- **Checked citations.** The model cites passages with `[S1]`-style markers. The app checks each marker against the passages that were actually retrieved, so a location shown to you always exists in the document.
- **Source viewer.** PDFs (and Word files converted to PDF) show the real page with the passage highlighted. Other files show the passage with the paragraphs around it.
- **Summarize.** Choose a language and an output type: PDF, Word or Text. The type is preselected to match your upload. Long documents are summarised part by part and combined. If a document is too long to cover, the summary says where it stops.
- **Voice input.** The mic button turns speech into text in the question box. You can edit it before sending. Pick the speaking language next to the mic.
- **Recent conversations.** Chats are saved and grouped by Today, Yesterday and so on. You can reopen, rename and delete them.

**Supported files:** `.pdf`, `.docx`, `.xlsx`, `.xlsm`, `.pptx`, `.txt`, `.md`, `.csv`, `.json`, `.html`, `.htm` (up to 20 MB by default).

**Summary languages:** English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati, Spanish, French and German. You can also type any other language name.

## Run it

You need Python and a PostgreSQL database.

1. Create and activate a virtual environment.

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   On macOS or Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install the packages.

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` (next to `app.py`) and fill in your own values. These three are required:

   ```
   FLASK_SECRET_KEY=...
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
   GEMINI_API_KEY=...
   ```

   Never commit `.env`; it is listed in `.gitignore`.

4. Start it and open http://127.0.0.1:5000

   ```bash
   python app.py
   ```

Tables are created automatically on start. If you used the first version, your old chats are kept and grouped into one conversation per document.

The first question or upload can be slow, because the embedding model is downloaded and loaded the first time.

## Settings

All settings go in `.env`. Only the first three are required; the rest are optional.

| Setting | Default | What it does |
|---|---|---|
| `FLASK_SECRET_KEY` | none (required) | Signs the session cookie. Use a long random value. |
| `DATABASE_URL` | none (required) | PostgreSQL connection string. |
| `GEMINI_API_KEY` | none (required) | Your Gemini API key. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model used for answers and summaries. |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model for retrieval. |
| `RETRIEVAL_TOP_K` | `5` | Passages retrieved per question. |
| `LLM_MAX_TOKENS` | `900` | Maximum length of an answer. |
| `SUMMARY_BATCH_CHARS` | `40000` | Text size of each part when summarising. |
| `SUMMARY_MAX_BATCHES` | `10` | Maximum parts per summary. |
| `SUMMARY_MAX_TOKENS` | `2500` | Maximum length of a summary. |
| `MAX_UPLOAD_MB` | `20` | Largest file accepted. |
| `UPLOAD_FOLDER`, `INDEX_FOLDER`, `EXPORT_FOLDER` | `uploads`, `indexes`, `exports` | Where files are stored. |
| `PDF_FONT_DIR` | empty | Folder with fonts for PDF summaries. |
| `SOFFICE_PATH` | empty | Path to LibreOffice, if it is not found automatically. |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS. |
| `HOST`, `PORT` | `127.0.0.1`, `5000` | Where the server listens. |

## How answers are produced

1. The upload is read by a file-specific extractor that keeps page, paragraph, sheet, row or slide locations.
2. The text is cut into chunks of up to about 1,100 characters with 180 characters of overlap. Each chunk keeps its location.
3. Chunks are embedded with sentence-transformers and stored in a FAISS index saved to disk. If FAISS is not installed, plain NumPy search gives the same results.
4. For each question, the closest chunks are sent to Gemini together with the question. The reply is checked and its `[S#]` markers are turned into clickable locations.

## Things to know

**Hindi, Tamil and other Indian languages**
- *Questions:* the default embedding model is English-focused, so retrieval for Hindi or Tamil questions is weak. Set `EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` in `.env`. Documents already uploaded must be uploaded again, because the saved index was built with the old model.
- *PDF summaries:* the PDF needs a font that contains the letters. On Windows the code finds `Nirmala.ttf` on its own. Elsewhere, put Noto Sans fonts in the `fonts/` folder (see `fonts/README.txt`). Word and Text summaries do not need this.

**Voice input** uses the browser's own speech recognition. It works in Chrome and Edge, needs internet, and Chrome sends the audio to Google for recognition. It is not available in Firefox.

**Page numbers in Word** follow Word's own layout when the file was saved by Word. LibreOffice pagination can differ slightly from Word.

**Paragraphs in PDF** are text blocks found by PyMuPDF. A paragraph that a PDF splits into several blocks (for example across columns) will count as several.

**Scanned PDFs** have no text layer, so they cannot be read without OCR first.

**Storage.** Uploads are saved in `uploads/`, search indexes in `indexes/`, summary files in `exports/`. Deleting the last conversation for a document removes its files. Hosts with temporary disks will lose these on redeploy; the app rebuilds an index from the upload if only the index is missing.

**Security.** Each browser gets its own private identity in a cookie, and every request checks that the conversation, document or summary belongs to it. There are no user accounts yet, so clearing cookies loses access to old chats. Add real sign-in before using confidential documents with other people. The server listens on `127.0.0.1` by default; set `HOST=0.0.0.0` only if you mean to expose it.

**Data leaves your machine.** Retrieved passages and questions are sent to Gemini to generate answers and summaries.

## Deploying

A `Procfile` is included for hosts that support it:

```
web: gunicorn app:app --workers 1 --threads 4 --timeout 300
```

Set the environment variables from `.env.example` on the host, use HTTPS with `SESSION_COOKIE_SECURE=true`, and remember that temporary disks lose uploads and indexes on redeploy.

## API

| Route | Purpose |
|---|---|
| `GET /` | The web page |
| `GET /api/health`, `GET /api/config` | Status and settings for the frontend |
| `POST /api/upload` | Upload and index a document |
| `GET /api/conversations` | List saved conversations |
| `GET /api/conversations/<id>` | Open one conversation |
| `PATCH` / `DELETE /api/conversations/<id>` | Rename or delete a conversation |
| `POST /api/ask` | Ask a question (max 2,000 characters) |
| `POST /api/summarize` | Create a summary as PDF, Word or Text |
| `GET /api/summaries/<id>/download` | Download a summary file |
| `GET /api/documents/<id>/page/<n>.png` | PDF page image for the viewer |
| `GET /api/documents/<id>/context` | Passage with surrounding paragraphs |

## Project layout

```
app.py            routes: upload, conversations, ask, summarize, viewer
rag_engine.py     chunking with page/paragraph, saved index, retrieval, answers
extractors.py     file readers that keep page/paragraph/row locations
citations.py      checks [S1]-style markers against the real passages
summarizer.py     long-document summaries with checked locations
exporter.py       PDF / Word / Text summary files
llm.py            the one place that calls Gemini
database.py       PostgreSQL: documents, conversations, messages, summaries
languages.py      language list shared by backend and frontend
templates/, static/   the interface
tests/            automated tests (they use an in-memory database and fake model)
fonts/            fonts for PDF summaries in Indian languages
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover location extraction for text and Word, citation checking, summaries, file export, and the API routes. They replace PostgreSQL, Gemini and the embedding model with simple stand-ins, so they do not prove those three work. Check them yourself with `test_db.py` and `test_gemini.py`.

## Not done yet (planned)

- Strict document-only mode with an evidence-sufficiency check
- Claim-by-claim verification of answers
- Contradiction and missing-information detection
- Evidence-strength indicators
- A hallucination testing lab

The `[S1]` marker check is a first step: it guarantees that a shown location is real, but not that the cited passage actually supports the statement.
