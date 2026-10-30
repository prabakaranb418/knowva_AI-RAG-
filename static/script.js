(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const JSON_HEADERS = { "Content-Type": "application/json" };

  const el = {
    shell: $("#shell"), sidebar: $("#sidebar"), scrim: $("#scrim"), history: $("#history"),
    newChat: $("#newChatBtn"), menuBtn: $("#menuBtn"), closeSidebar: $("#closeSidebarBtn"), themeBtn: $("#themeBtn"),
    docTitle: $("#docTitle"), docType: $("#docType"), docName: $("#docName"),
    topActions: $("#topActions"), summarizeBtn: $("#summarizeBtn"),
    emptyStage: $("#emptyStage"), chatStage: $("#chatStage"),
    dropzone: $("#dropzone"), fileInput: $("#fileInput"), uploadStatus: $("#uploadStatus"),
    uploadStatusText: $("#uploadStatusText"), uploadError: $("#uploadError"),
    transcript: $("#transcript"), inner: $("#transcriptInner"),
    composer: $("#composer"), input: $("#questionInput"), count: $("#charCount"), send: $("#sendBtn"),
    mic: $("#micBtn"), speechLang: $("#speechLang"), hint: $("#composerHint"),
    viewer: $("#viewer"), viewerLabel: $("#viewerLabel"), viewerFile: $("#viewerFile"),
    viewerTabs: $("#viewerTabs"), viewerBody: $("#viewerBody"), closeViewer: $("#closeViewerBtn"),
    dialog: $("#summaryDialog"), sumForm: $("#summaryForm"), sumFile: $("#sumFile"), sumLang: $("#sumLang"),
    sumLangOther: $("#sumLangOther"), sumFormats: $("#sumFormats"), sumFormatHint: $("#sumFormatHint"),
    sumLangHint: $("#sumLangHint"), sumError: $("#sumError"), sumGo: $("#sumGo"), sumCancel: $("#sumCancel"),
    toast: $("#toast"),
  };

  const ICON = {
    pencil: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l1-4 8-8 3 3-8 8-4 1z"/></svg>',
    trash: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"/></svg>',
  };

  const state = { config: null, conversations: [], activeId: null, active: null, busy: false };
  const HINT = "Enter to send, Shift+Enter for a new line";

  /* ---------------------------------------------------------------- small helpers */

  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* storage unavailable */ } },
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  async function api(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch {
      throw new Error("Can't reach the server. Check that it is running, then try again.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The request could not be completed.");
    return data;
  }

  let toastTimer;
  function toast(message) {
    el.toast.textContent = message;
    el.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.toast.classList.remove("show"), 3600);
  }

  function byId(id) { return state.conversations.find((c) => c.id === id); }

  /* ---------------------------------------------------------------- theme */

  function applyTheme(mode) {
    if (mode === "light" || mode === "dark") document.documentElement.dataset.theme = mode;
    else delete document.documentElement.dataset.theme;
    el.themeBtn.textContent = `Theme: ${mode}`;
  }
  let themeMode = store.get("knowva.theme") || "auto";
  if (!["auto", "light", "dark"].includes(themeMode)) themeMode = "auto";
  applyTheme(themeMode);
  el.themeBtn.addEventListener("click", () => {
    themeMode = { auto: "light", light: "dark", dark: "auto" }[themeMode];
    store.set("knowva.theme", themeMode);
    applyTheme(themeMode);
  });

  /* ---------------------------------------------------------------- sidebar */

  function groupLabel(iso) {
    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const days = Math.round((startOfDay(new Date()) - startOfDay(new Date(iso))) / 86400000);
    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 8) return "Previous 7 days";
    return "Older";
  }

  function itemHTML(c) {
    const active = c.id === state.activeId;
    return `<div class="chat-item${active ? " active" : ""}" data-id="${esc(c.id)}">
      <button class="chat-open" type="button"${active ? ' aria-current="true"' : ""}>
        <span class="chat-title">${esc(c.title)}</span><span class="chat-file">${esc(c.filename)}</span>
      </button>
      <div class="chat-tools">
        <button class="icon-btn" type="button" data-act="rename" aria-label="Rename conversation">${ICON.pencil}</button>
        <button class="icon-btn" type="button" data-act="delete" aria-label="Delete conversation">${ICON.trash}</button>
      </div></div>`;
  }

  function renderHistory() {
    if (!state.conversations.length) {
      el.history.innerHTML = '<p class="history-empty">Conversations you start will be listed here, so you can come back to them.</p>';
      return;
    }
    const groups = [];
    const seen = new Map();
    for (const c of state.conversations) {
      const label = groupLabel(c.updated_at);
      if (!seen.has(label)) { const g = { label, items: [] }; seen.set(label, g); groups.push(g); }
      seen.get(label).items.push(c);
    }
    el.history.innerHTML = groups
      .map((g) => `<section class="history-group"><h2>${esc(g.label)}</h2>${g.items.map(itemHTML).join("")}</section>`)
      .join("");
  }

  async function loadConversations() {
    try {
      const data = await api("/api/conversations");
      state.conversations = data.conversations;
    } catch (error) {
      toast(error.message);
    }
    renderHistory();
  }

  function startRename(item) {
    const conv = byId(item.dataset.id);
    if (!conv) return;
    item.innerHTML = `<input class="chat-rename" maxlength="120" value="${esc(conv.title)}" aria-label="Conversation name">`;
    const input = $("input", item);
    input.focus();
    input.select();
    let finished = false;
    const finish = async (save) => {
      if (finished) return;
      finished = true;
      const title = input.value.trim();
      if (save && title && title !== conv.title) {
        try {
          const result = await api(`/api/conversations/${conv.id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify({ title }) });
          conv.title = result.title;
        } catch (error) { toast(error.message); }
      }
      renderHistory();
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); finish(true); }
      else if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  function askDelete(item) {
    item.innerHTML = `<div class="chat-confirm"><span>Delete this chat?</span>
      <button type="button" class="yes" data-act="confirm-delete">Delete</button>
      <button type="button" data-act="cancel-delete">Keep</button></div>`;
    $("button", item).focus();
  }

  async function deleteConversation(id) {
    try {
      await api(`/api/conversations/${id}`, { method: "DELETE" });
      state.conversations = state.conversations.filter((c) => c.id !== id);
      if (state.activeId === id) showEmpty();
      renderHistory();
      toast("Conversation deleted.");
    } catch (error) {
      toast(error.message);
      renderHistory();
    }
  }

  el.history.addEventListener("click", (event) => {
    const item = event.target.closest(".chat-item");
    if (!item) return;
    const action = event.target.closest("[data-act]")?.dataset.act;
    if (action === "rename") startRename(item);
    else if (action === "delete") askDelete(item);
    else if (action === "confirm-delete") deleteConversation(item.dataset.id);
    else if (action === "cancel-delete") renderHistory();
    else if (event.target.closest(".chat-open")) { openConversation(item.dataset.id); closeSidebarOnMobile(); }
  });

  function openSidebar() { el.sidebar.classList.add("open"); el.scrim.hidden = false; }
  function closeSidebarOnMobile() { el.sidebar.classList.remove("open"); el.scrim.hidden = true; }
  el.menuBtn.addEventListener("click", openSidebar);
  el.closeSidebar.addEventListener("click", closeSidebarOnMobile);
  el.scrim.addEventListener("click", closeSidebarOnMobile);
  el.newChat.addEventListener("click", () => { showEmpty(); closeSidebarOnMobile(); });

  /* ---------------------------------------------------------------- views */

  function showEmpty() {
    stopVoice();
    closeViewer();
    state.activeId = null;
    state.active = null;
    store.set("knowva.active", "");
    el.docTitle.hidden = true;
    el.topActions.hidden = true;
    el.chatStage.hidden = true;
    el.emptyStage.hidden = false;
    renderHistory();
  }

  function showChat() {
    const conv = state.active.conversation;
    el.docType.textContent = conv.file_type;
    el.docName.textContent = conv.filename;
    el.docName.title = conv.filename;
    el.docTitle.hidden = false;
    el.topActions.hidden = false;
    el.emptyStage.hidden = true;
    el.chatStage.hidden = false;
    store.set("knowva.active", conv.id);
  }

  async function openConversation(id) {
    if (state.busy) return;
    stopVoice();
    closeViewer();
    let data;
    try {
      data = await api(`/api/conversations/${id}`);
    } catch (error) {
      toast(error.message);
      return;
    }
    state.activeId = id;
    state.active = data;
    showChat();
    renderTranscript();
    renderHistory();
    el.input.focus();
  }

  /* ---------------------------------------------------------------- rendering messages */

  function inline(escaped, sources) {
    return escaped
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[S(\d+)\]/g, (_m, n) => {
        const source = (sources || []).find((s) => s.number === Number(n));
        if (!source) return "";
        return `<button class="cite" type="button" data-number="${source.number}" title="Open ${esc(source.location_label)}">${esc(source.short_label)}</button>`;
      })
      .replace(/\[((?:p\.\d+|¶\d+)[^\]]*)\]/g, '<span class="loc">[$1]</span>');
  }

  function richText(text, sources) {
    let html = "";
    let list = null;
    let paragraph = [];
    const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
    const flush = () => { if (paragraph.length) { html += `<p>${inline(paragraph.join(" "), sources)}</p>`; paragraph = []; } };
    for (const raw of esc(text).split(/\r?\n/)) {
      const line = raw.trim();
      let match;
      if (!line) { flush(); closeList(); }
      else if ((match = line.match(/^[-*•]\s+(.*)$/))) {
        flush();
        if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
        html += `<li>${inline(match[1], sources)}</li>`;
      } else if ((match = line.match(/^\d+[.)]\s+(.*)$/))) {
        flush();
        if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
        html += `<li>${inline(match[1], sources)}</li>`;
      } else { closeList(); paragraph.push(line); }
    }
    flush();
    closeList();
    return html;
  }

  function blocksHTML(blocks) {
    let html = "";
    let open = false;
    for (const block of blocks) {
      if (block.type !== "bullet" && open) { html += "</ul>"; open = false; }
      const text = inline(esc(block.text), []);
      if (block.type === "heading") html += `<h3>${text}</h3>`;
      else if (block.type === "bullet") { if (!open) { html += "<ul>"; open = true; } html += `<li>${text}</li>`; }
      else html += `<p>${text}</p>`;
    }
    return open ? html + "</ul>" : html;
  }

  function sourcesHTML(message) {
    const sources = message.sources || [];
    if (!sources.length) return "";
    const cited = new Set((message.meta && message.meta.cited) || []);
    const items = sources.map((s) => {
      const used = !cited.size || cited.has(s.number);
      const score = typeof s.relevance_score === "number" ? ` · match ${s.relevance_score.toFixed(2)}` : "";
      return `<li class="source${used ? "" : " unused"}">
        <div class="source-head">
          <button class="source-open" type="button" data-number="${s.number}">${esc(s.location_label || "Source")}</button>
          <span class="source-meta">${cited.size ? (used ? "Cited" : "Not cited") : ""}${esc(score)}</span>
        </div><p>${esc(s.passage)}</p></li>`;
    }).join("");
    return `<details class="sources"><summary>Passages searched (${sources.length})</summary><ul class="source-list">${items}</ul></details>`;
  }

  function turnInner(message) {
    if (message.kind === "summary") {
      const meta = message.meta || {};
      const body = meta.blocks ? blocksHTML(meta.blocks) : richText(message.answer, []);
      const download = meta.summary_id
        ? `<a class="btn primary" href="/api/summaries/${esc(meta.summary_id)}/download">Download ${esc(meta.format_label || "file")}</a>` : "";
      const notes = (meta.notes || []).map((n) => `<p class="summary-note">${esc(n)}</p>`).join("");
      const failure = meta.export_error ? `<p class="summary-note warn">${esc(meta.export_error)}</p>` : "";
      return `<p class="q">${esc(message.question)}</p><div class="a">${body}</div>
        ${download ? `<div class="summary-tools">${download}</div>` : ""}${failure}${notes}`;
    }
    return `<p class="q">${esc(message.question)}</p><div class="a">${richText(message.answer, message.sources)}</div>${sourcesHTML(message)}`;
  }

  function addTurn(html, message) {
    const article = document.createElement("article");
    article.className = "turn";
    article.innerHTML = html;
    if (message) article._message = message;
    el.inner.appendChild(article);
    scrollToEnd();
    return article;
  }

  function scrollToEnd() { requestAnimationFrame(() => { el.transcript.scrollTop = el.transcript.scrollHeight; }); }

  function renderTranscript() {
    const { document: doc, messages, index_error: indexError, conversation } = state.active;
    el.inner.innerHTML = "";
    if (indexError) el.inner.insertAdjacentHTML("beforeend", `<p class="notice warn" role="alert">${esc(indexError)}</p>`);
    for (const note of (doc && doc.notes) || []) el.inner.insertAdjacentHTML("beforeend", `<p class="notice">${esc(note)}</p>`);
    if (!messages.length) {
      el.inner.insertAdjacentHTML("beforeend",
        `<p class="notice">${esc(conversation.filename)} is ready. Ask a question below, or choose Summarize for an overview.</p>`);
    }
    for (const message of messages) addTurn(turnInner(message), message);
    el.transcript.scrollTop = el.transcript.scrollHeight;
  }

  el.inner.addEventListener("click", (event) => {
    const trigger = event.target.closest(".cite, .source-open");
    if (!trigger) return;
    const turn = trigger.closest(".turn");
    const message = turn && turn._message;
    const source = message && (message.sources || []).find((s) => s.number === Number(trigger.dataset.number));
    if (source) openViewer(source);
  });

  /* ---------------------------------------------------------------- asking */

  function setBusy(value) { state.busy = value; el.send.disabled = value; }

  function autosize() {
    el.input.style.height = "auto";
    el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
  }
  function updateCount() { el.count.textContent = `${el.input.value.length}/2000`; }

  async function ask(question) {
    const text = question.trim();
    if (!text || state.busy || !state.activeId) return;
    stopVoice();
    setBusy(true);
    const turn = addTurn(`<p class="q">${esc(text)}</p><div class="a"><div class="working"><span class="bar"></span><span>Searching the document…</span></div></div>`);
    el.input.value = "";
    autosize();
    updateCount();
    try {
      const message = await api("/api/ask", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ conversation_id: state.activeId, question: text }) });
      state.active.messages.push(message);
      turn._message = message;
      turn.innerHTML = turnInner(message);
      scrollToEnd();
      loadConversations();
    } catch (error) {
      $(".a", turn).innerHTML = `<p class="error-line">${esc(error.message)}</p>`;
    } finally {
      setBusy(false);
    }
  }

  el.composer.addEventListener("submit", (event) => { event.preventDefault(); ask(el.input.value); });
  el.input.addEventListener("input", () => { autosize(); updateCount(); });
  el.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); el.composer.requestSubmit(); }
  });

  /* ---------------------------------------------------------------- voice input */

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;

  function setupSpeechLanguages() {
    const options = state.config.languages.map((l) => ({
      code: l.speech, label: l.name === "English" ? "English (India)" : `${l.native} (${l.name})`,
    }));
    options.splice(1, 0, { code: "en-US", label: "English (US)" });
    el.speechLang.innerHTML = options.map((o) => `<option value="${esc(o.code)}">${esc(o.label)}</option>`).join("");
    const saved = store.get("knowva.speech");
    const browser = (navigator.language || "en-IN").split("-")[0];
    const preferred = options.find((o) => o.code === saved) || options.find((o) => o.code.startsWith(browser + "-")) || options[0];
    el.speechLang.value = preferred.code;
  }

  function setListening(on) {
    el.mic.setAttribute("aria-pressed", String(on));
    el.mic.setAttribute("aria-label", on ? "Stop listening" : "Speak your question");
    el.composer.classList.toggle("listening", on);
    el.hint.textContent = on ? "Listening. Speak now, then tap the mic to stop." : HINT;
  }

  function startVoice() {
    if (!SpeechRecognition || recognition) return;
    const instance = new SpeechRecognition();
    instance.lang = el.speechLang.value;
    instance.continuous = true;
    instance.interimResults = true;
    const base = el.input.value ? el.input.value.replace(/\s+$/, "") + " " : "";
    instance.onstart = () => setListening(true);
    instance.onresult = (event) => {
      let spoken = "";
      for (let i = 0; i < event.results.length; i += 1) spoken += event.results[i][0].transcript;
      el.input.value = (base + spoken).slice(0, 2000);
      autosize();
      updateCount();
    };
    instance.onerror = (event) => {
      const messages = {
        "not-allowed": "Microphone access is blocked. Allow it from the address bar, then try again.",
        "service-not-allowed": "Microphone access is blocked. Allow it from the address bar, then try again.",
        "no-speech": "No speech was heard. Tap the mic and try again.",
        "audio-capture": "No microphone was found.",
        "network": "Speech recognition needs an internet connection.",
        "language-not-supported": "This browser can't recognise that language. Pick another.",
      };
      if (messages[event.error]) toast(messages[event.error]);
    };
    instance.onend = () => { setListening(false); recognition = null; };
    recognition = instance;
    try { instance.start(); } catch { recognition = null; setListening(false); }
  }

  function stopVoice() {
    if (!recognition) return;
    try { recognition.stop(); } catch { /* already stopped */ }
  }

  el.mic.addEventListener("click", () => { if (recognition) stopVoice(); else startVoice(); });
  el.speechLang.addEventListener("change", () => { store.set("knowva.speech", el.speechLang.value); stopVoice(); });

  /* ---------------------------------------------------------------- upload */

  function showUploadError(message) { el.uploadError.textContent = message; el.uploadError.hidden = false; }

  async function uploadFile(file) {
    if (!file) return;
    el.uploadError.hidden = true;
    const extension = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!state.config.extensions.includes(extension)) {
      showUploadError("That file type isn't supported. Use PDF, Word, Excel, PowerPoint, text, CSV, JSON or HTML.");
      return;
    }
    if (file.size > state.config.max_upload_mb * 1024 * 1024) {
      showUploadError(`That file is larger than ${state.config.max_upload_mb} MB.`);
      return;
    }
    el.uploadStatus.hidden = false;
    el.uploadStatusText.textContent = "Reading and indexing your file. The first upload can take longer while the search model loads.";
    const form = new FormData();
    form.append("file", file);
    try {
      const data = await api("/api/upload", { method: "POST", body: form });
      state.activeId = data.conversation.id;
      state.active = { conversation: data.conversation, document: data.document, messages: [], index_error: null };
      await loadConversations();
      showChat();
      renderTranscript();
      el.input.focus();
    } catch (error) {
      showUploadError(error.message);
    } finally {
      el.uploadStatus.hidden = true;
      el.fileInput.value = "";
    }
  }

  el.fileInput.addEventListener("change", (event) => uploadFile(event.target.files[0]));
  ["dragenter", "dragover"].forEach((name) => el.dropzone.addEventListener(name, (event) => { event.preventDefault(); el.dropzone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((name) => el.dropzone.addEventListener(name, (event) => { event.preventDefault(); el.dropzone.classList.remove("dragover"); }));
  el.dropzone.addEventListener("drop", (event) => uploadFile(event.dataTransfer.files[0]));
  el.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); el.fileInput.click(); }
  });
  // Dropping a file outside the drop area should not make the browser open it.
  ["dragover", "drop"].forEach((name) => window.addEventListener(name, (event) => { if (!el.dropzone.contains(event.target)) event.preventDefault(); }));

  /* ---------------------------------------------------------------- source viewer */

  let viewerSource = null;
  let viewerToken = 0;

  function openViewer(source) {
    viewerSource = source;
    el.viewerLabel.textContent = source.location_label || "Source";
    el.viewerFile.textContent = source.filename || "";
    const canShowPage = Boolean(source.can_render_page && source.chunk_id && source.page);
    el.viewerTabs.hidden = !canShowPage;
    el.viewer.classList.add("open");
    el.viewer.setAttribute("aria-hidden", "false");
    el.shell.classList.add("viewer-open");
    setViewerTab(canShowPage ? "page" : "text");
  }

  function closeViewer() {
    viewerToken += 1;
    el.viewer.classList.remove("open");
    el.viewer.setAttribute("aria-hidden", "true");
    el.shell.classList.remove("viewer-open");
  }

  function setViewerTab(tab) {
    for (const button of el.viewerTabs.querySelectorAll("button")) button.setAttribute("aria-selected", String(button.dataset.tab === tab));
    if (tab === "page") showPageImage(); else showText();
  }

  function showPageImage() {
    const token = ++viewerToken;
    const source = viewerSource;
    const documentId = state.active.conversation.document_id;
    el.viewerBody.innerHTML = '<p class="viewer-loading">Loading page…</p>';
    const image = new Image();
    image.alt = `${source.location_label} of ${source.filename}, with the cited passage marked`;
    image.onload = () => {
      if (token !== viewerToken) return;
      el.viewerBody.innerHTML = "";
      el.viewerBody.appendChild(image);
      el.viewerBody.insertAdjacentHTML("beforeend", '<p class="viewer-note">The cited passage is marked when it can be found on the page. Switch to Text to read it on its own.</p>');
    };
    image.onerror = () => { if (token === viewerToken) { toast("This page could not be shown. Showing the text instead."); showText(); } };
    image.src = `/api/documents/${encodeURIComponent(documentId)}/page/${source.page}.png?chunk=${source.chunk_id}`;
  }

  async function showText() {
    const token = ++viewerToken;
    const source = viewerSource;
    const documentId = state.active.conversation.document_id;
    const own = `<div class="context"><p class="current"><span class="where">${esc(source.location_label)}</span><span class="hl">${esc(source.passage)}</span></p></div>`;
    if (!source.chunk_id) { el.viewerBody.innerHTML = own; return; }
    el.viewerBody.innerHTML = '<p class="viewer-loading">Loading…</p>';
    try {
      const data = await api(`/api/documents/${encodeURIComponent(documentId)}/context?chunk=${source.chunk_id}`);
      if (token !== viewerToken) return;
      const around = (item) => `<p><span class="where">${esc(item.label)}</span>${esc(item.text)}</p>`;
      el.viewerBody.innerHTML = `<div class="context">${data.before.map(around).join("")}
        <p class="current"><span class="where">${esc(data.current.label)}</span><span class="hl">${esc(data.current.text)}</span></p>
        ${data.after.map(around).join("")}</div>`;
      $(".current", el.viewerBody).scrollIntoView({ block: "center" });
    } catch {
      if (token === viewerToken) el.viewerBody.innerHTML = own;
    }
  }

  el.viewerTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) setViewerTab(button.dataset.tab);
  });
  el.closeViewer.addEventListener("click", closeViewer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && el.viewer.classList.contains("open") && !el.dialog.open) closeViewer();
  });

  /* ---------------------------------------------------------------- summarize */

  let chosenFormat = "pdf";

  function formatFor(fileType) {
    const type = (fileType || "").toLowerCase();
    if (type === "pdf") return "pdf";
    if (type === "docx") return "docx";
    if (type === "txt" || type === "md") return "txt";
    return null;
  }

  function renderFormats() {
    el.sumFormats.innerHTML = state.config.formats.map((f) => `
      <label class="choice"><input type="radio" name="sumFormat" value="${esc(f.id)}"${f.id === chosenFormat ? " checked" : ""}><span>${esc(f.label)}</span></label>`).join("");
  }

  function updateLanguageHint() {
    const value = el.sumLang.value;
    el.sumLangOther.hidden = value !== "__other";
    el.sumLangHint.hidden = value === "English";
  }

  function openSummaryDialog() {
    const conv = state.active.conversation;
    const matched = formatFor(conv.file_type);
    chosenFormat = matched || "pdf";
    el.sumFile.textContent = conv.filename;
    el.sumFormatHint.textContent = matched
      ? `Matches your uploaded ${conv.file_type} file. You can choose another type.`
      : `Your file is ${conv.file_type}. Choose the type you want.`;
    renderFormats();
    el.sumError.hidden = true;
    updateLanguageHint();
    el.dialog.showModal();
  }

  el.summarizeBtn.addEventListener("click", openSummaryDialog);
  el.sumCancel.addEventListener("click", () => el.dialog.close());
  el.dialog.addEventListener("click", (event) => { if (event.target === el.dialog) el.dialog.close(); });
  el.sumLang.addEventListener("change", () => { updateLanguageHint(); if (!el.sumLangOther.hidden) el.sumLangOther.focus(); });

  el.sumForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy) return;
    const language = el.sumLang.value === "__other" ? el.sumLangOther.value.trim() : el.sumLang.value;
    const format = (el.sumForm.querySelector('input[name="sumFormat"]:checked') || {}).value;
    if (!language) { el.sumError.textContent = "Type the language you want."; el.sumError.hidden = false; return; }
    el.sumError.hidden = true;
    store.set("knowva.sumLang", el.sumLang.value);
    setBusy(true);
    el.sumGo.disabled = true;
    el.sumGo.classList.add("busy");
    el.sumGo.textContent = "Reading the document…";
    try {
      const message = await api("/api/summarize", {
        method: "POST", headers: JSON_HEADERS,
        body: JSON.stringify({ conversation_id: state.activeId, language, format }),
      });
      state.active.messages.push(message);
      addTurn(turnInner(message), message);
      el.dialog.close();
      if (message.meta && message.meta.export_error) toast("The summary is ready, but the file could not be made.");
      loadConversations();
    } catch (error) {
      el.sumError.textContent = error.message;
      el.sumError.hidden = false;
    } finally {
      setBusy(false);
      el.sumGo.disabled = false;
      el.sumGo.classList.remove("busy");
      el.sumGo.textContent = "Create summary";
    }
  });

  /* ---------------------------------------------------------------- start */

  async function init() {
    try {
      state.config = await api("/api/config");
    } catch (error) {
      showUploadError(error.message);
      return;
    }
    el.fileInput.accept = state.config.extensions.join(",");
    el.sumLang.innerHTML = state.config.languages
      .map((l) => `<option value="${esc(l.name)}">${esc(l.name === l.native ? l.name : `${l.name} (${l.native})`)}</option>`)
      .join("") + '<option value="__other">Other…</option>';
    const savedLanguage = store.get("knowva.sumLang");
    if (savedLanguage && [...el.sumLang.options].some((o) => o.value === savedLanguage)) el.sumLang.value = savedLanguage;

    setupSpeechLanguages();
    if (!SpeechRecognition) {
      el.mic.disabled = true;
      el.mic.title = "Voice input works in Chrome and Edge.";
      el.speechLang.hidden = true;
      el.hint.textContent = "Voice input needs Chrome or Edge. " + HINT;
    }

    await loadConversations();
    const last = store.get("knowva.active");
    if (last && byId(last)) openConversation(last);
  }

  init();
})();
