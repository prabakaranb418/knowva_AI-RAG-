# Knowva

Ask questions about a document and see the page and paragraph each answer came from.

Flask backend, plain HTML/CSS/JavaScript frontend, Gemini for answers, sentence-transformers + FAISS for retrieval, PostgreSQL for documents and history.

## What it does

- **Exact locations.** Every answer carries markers such as `p.4 ¶2`. Click one to open the source.
  - PDF: page and paragraph (a paragraph is a text block on that page).
  - Word: page and paragraph. Pages come from the page breaks Word saved in the file. If the file has none, LibreOffice (if installed) makes a PDF copy to get pages. If neither works, you get paragraph numbers only, and the app says so.
  - Text and Markdown: paragraph numbers (paragraphs are separated by blank lines).
  - Excel, PowerPoint, CSV, JSON, HTML: sheet and row, slide, row, JSON path, HTML element.
- **Source viewer.** PDFs (and Word files converted to PDF) show the real page with the passage highlighted. Other files show the passage with the paragraphs around it.
- **Summarize.** Choose a language and an output type: PDF, Word or Text. The type is preselected to match your upload. Long documents are summarised part by part and combined. If a document is too long to cover, the summary says where it stops.
- **Voice input.** The mic button turns speech into text in the question box. You can edit it before sending. Pick the speaking language next to the mic.
- **Recent conversations.** Chats are saved and grouped by Today, Yesterday and so on. You can reopen, rename and delete them.

## Run it

1. Create and activate a virtual environment.

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the packages.

   ```bash
   pip install -r requirements.txt
   ```

3. Make your own `.env` next to `app.py` (this zip does not contain one). `.env.example` lists every setting. These three are required:

   ```
   FLASK_SECRET_KEY=...
   DATABASE_URL=postgresql://...
   GEMINI_API_KEY=...
   ```

4. Start it and open http://127.0.0.1:5000

   ```bash
   python app.py
   ```

Tables are created on start. If you used the first version, your old chats are kept and grouped into one conversation per document.

## Things to know

**Hindi, Tamil and other Indian languages**
- *Questions:* the default embedding model is English-focused, so retrieval for Hindi or Tamil questions is weak. Set `EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` in `.env`. Documents already uploaded must be uploaded again, because the saved index was built with the old model.
- *PDF summaries:* the PDF needs a font that contains the letters. On Windows the code finds `Nirmala.ttf` on its own. Elsewhere, put Noto Sans fonts in the `fonts/` folder (see `fonts/README.txt`). Word and Text summaries do not need this.

**Voice input** uses the browser's own speech recognition. It works in Chrome and Edge, needs internet, and Chrome sends the audio to Google for recognition. It is not available in Firefox.

**Page numbers in Word** follow Word's own layout when the file was saved by Word. LibreOffice pagination can differ slightly from Word.

**Paragraphs in PDF** are text blocks found by PyMuPDF. A paragraph that a PDF splits into several blocks (for example across columns) will count as several.

**Storage.** Uploads are saved in `uploads/`, search indexes in `indexes/`, summary files in `exports/`. Deleting the last conversation for a document removes its files. Hosts with temporary disks will lose these on redeploy; the app rebuilds an index from the upload if only the index is missing.

**Security.** Each browser gets its own private identity in a cookie, and every request checks that the conversation, document or summary belongs to it. There are no user accounts yet, so clearing cookies loses access to old chats. Add real sign-in before using confidential documents with other people. The server listens on 127.0.0.1 by default; set `HOST=0.0.0.0` only if you mean to expose it.

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
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover location extraction for text and Word, citation checking, summaries, file export, and the API routes. They replace PostgreSQL, Gemini and the embedding model with simple stand-ins, so they do not prove those three work. Check them yourself with `test_db.py` and `test_gemini.py`.

## What is not done yet

These come from your master prompt and are the next stages: strict document-only mode with an evidence-sufficiency check, claim-by-claim verification, contradiction and missing-information detection, evidence-strength indicators, and the hallucination testing lab. The `[S1]` marker check is a first step: it guarantees that a shown location is real, but not that the cited passage actually supports the statement.
