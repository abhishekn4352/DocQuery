# DocQuery — Rewrite Report

This covers everything changed from the original prototype (documented in
the earlier *DocQuery Understanding Report*) to this rewrite. Every claim
about behavior below was verified by actually running it in a sandbox — the
methodology and its limits are in §12.

---

## 1. What was changed

The application was rebuilt around the same core idea and the same core
stack (FastAPI + LangChain + Chroma + Groq + local embeddings + plain
HTML/JS), per the "don't replace the architecture" instruction — nothing
was swapped out (no new database engine, no frontend framework, no new
LLM/vector provider). What changed is everything *around* that core:
persistence, security, document handling, retrieval quality, citations,
conversation memory, the API surface, the frontend, and test coverage.

The backend went from one 200-line script to a structured package
(config/database/routes/services/models/utils, ~1,565 lines). The two
separate servers (FastAPI + a standalone Flask contact form) became one.
The frontend went from three inconsistent pages to a two-page app
(dashboard + chat) sharing one config, one theme system, and one API
client. A 33-test pytest suite was added and is run as part of this report,
not just written.

## 2. Files created

```
backend/config.py                  backend/models/schemas.py
backend/database.py                backend/routes/chat.py
backend/main.py                    backend/routes/contact.py
backend/services/document_service.py   backend/routes/documents.py
backend/services/embedding_service.py  backend/routes/misc.py
backend/services/rag_service.py    backend/utils/errors.py
backend/services/vector_store.py   backend/utils/file_utils.py
backend/services/email_service.py  (+ __init__.py in each package)

frontend/src/api.js
frontend/src/theme.js
frontend/src/styles.css

tests/conftest.py                  tests/test_search.py
tests/test_documents.py            tests/test_security.py
tests/test_persistence.py

.env.example   requirements-dev.txt   pytest.ini   CHANGES.md (this file)
```

## 3. Files modified (replaced, same role)

- `README.md` — rewritten to match the actual new implementation.
- `.gitignore` — fixed to match the directories the app actually creates
  (`chroma_db/`, `document_store/`); the original said `chroma/`, which
  never matched anything.
- `requirements.txt` — every dependency pinned to a version confirmed
  installed and tested together (was fully unpinned).
- `frontend/config.js` — now the single, actually-used source of truth for
  the backend URL on every page.
- `frontend/index.html`, `frontend/chat.html` — rewritten (valid HTML,
  merged upload flow, evidence panel, document scope, new design).
- `frontend/src/components.js` — kept as the one shared UI-helpers module,
  rewritten so every page actually uses it (no more parallel copies).

## 4. Files deleted (and why)

| File | Why |
|---|---|
| `app.py` | The standalone Flask contact service. Merged into the main FastAPI app (`backend/routes/contact.py` + `backend/services/email_service.py`) — same feature, one process instead of two undocumented ones. |
| `frontend/upload.html` | Its functionality (drag-drop upload) was merged directly into the dashboard (`index.html`) rather than kept as a separate page — this is what let the "wrong port on the upload page" bug class disappear entirely rather than get patched. |
| `package.json`, `package-lock.json` (repo root) | Not part of the app — the lockfile's own `"name"` field was literally `"New folder"`, a clear accidental artifact from an unrelated local `npm install`. |
| `frontend/package.json`, `frontend/tailwind.config.js`, `frontend/src/input.css` | The local Tailwind build these supported was never actually run in the original (no `style.css` existed), and `chat.html` linked a stylesheet that didn't exist. Rather than fix a build pipeline nothing depended on, the app now uses the Tailwind CDN consistently everywhere it always effectively relied on anyway — one less moving part, no Node build step required to run the app. |

## 5. New features

- **DOCX upload support**, structure-aware (headings/paragraphs/tables), not just accepted-then-rejected.
- **Document dashboard**: per-document status (processing/ready/empty/failed), type, size, page/chunk counts, Ask/Download/Delete actions.
- **Working delete**: removes the file, its Chroma chunks, and its metadata row — verified not to touch any other document.
- **Document-scoped search**: ask about one specific file or all of them.
- **Real citations**: filename + page number (PDF) or section (DOCX) + a short excerpt, not just a bare filename.
- **Evidence panel**: shows the actual retrieved excerpts behind an answer.
- **Multi-turn conversation memory**: follow-up questions ("who proposed it?") are understood using recent conversation history, with a bounded turn window.
- **Conversation management**: multiple named conversations, persisted, listable, deletable.
- **Streaming answers** (SSE) with automatic fallback to a normal request if streaming can't be opened.
- **Structured errors** everywhere: `{"success": false, "error": {"code", "message"}}`, with human-readable messages.
- **One-command run**: the backend now also serves the frontend, so there's exactly one process to start.
- **Contact form** now works out of the box in the same process (previously silently required a second, undocumented server).

## 6. Bugs fixed

All of these were the specific, verified findings from the original
analysis report; each now has a passing regression test.

| # | Bug | Fix |
|---|---|---|
| 1 | Startup wiped `chroma_db`/`document_store` every restart | Startup only creates-if-missing; never deletes. Verified: documents, embeddings, and conversations all survive a simulated restart. |
| 2 | App could fail to start entirely — `python-multipart` missing | Added to `requirements.txt`; verified the app now starts and accepts uploads from a clean install. |
| 3 | Upload's "no text found" 400 silently became a 500 | Centralized exception handling; verified every error path returns its intended status code and a structured body. |
| 4 | Path traversal / arbitrary file write via upload filename | Client filename is now only ever a display label; every file on disk is named from a server-generated id. Verified: a `"../../../../tmp/..."` filename cannot escape the storage directory. |
| 5 | Non-UTF-8 `.txt` uploads crashed with a raw 500 | Encoding auto-detection fallback with a clean error only if genuinely undecodable. |
| 6 | Empty-PDF guard didn't actually catch scanned/image-only PDFs | Empty detection now checks actual extracted text length, not list emptiness. |
| 7 | PDF page numbers computed, then immediately discarded | Preserved end-to-end into citations. |
| 8 | "No results" search path skipped chat-history logging | Every path (including the greeting and no-result cases) is logged consistently. |
| 9 | `upload.html` hardcoded the wrong backend port | Upload is now part of the same page that already used the correct shared config, and streaming/asks all go through one `api.js` module. |
| 10 | Delete button called a nonexistent endpoint | `DELETE /api/documents/{id}` implemented, scoped, and tested. |
| 11 | Malformed HTML (nested doctype in `index.html`; tags before `<!DOCTYPE>` in `chat.html`) | Both pages are HTML-Tidy-clean (verified). |
| 12 | Contact form silently depended on an undocumented second server | Merged into the one backend/one port. |
| 13 | Flask debug mode left on | No longer applicable — Flask is gone; FastAPI's own debug/reload behavior is controlled by `RELOAD` in config, off by default in any non-dev use. |
| 14 | CORS: wildcard origin + credentials | Restricted to an explicit origin allow-list; verified an untrusted origin is not granted access while an allowed one is. |
| 15 | `.gitignore` didn't match real directory names | Fixed (`chroma_db/`, `document_store/` both present). |
| 16 | Fully unpinned dependencies | Pinned to a verified-working set. |
| 17 | Dead code (`HF_TOKEN` read-but-unused, `Request`/`secure_filename` unused imports, duplicate `createToast` implementations) | Removed/consolidated; `HF_TOKEN` now genuinely works (it's picked up automatically by `huggingface_hub` once present in the environment, which is the correct mechanism — verified). |
| 18 | `/settings/models/` listed models that could never actually be selected | Replaced with a read-only `/api/settings` reflecting the real configured model; no cosmetic selector for something that doesn't work. |

## 7. Security improvements

- Path traversal in uploads fixed and covered by an automated test.
- Server-side upload size **and** content-type (magic-byte) validation — not just client-side JS.
- CORS restricted to an explicit origin list (configurable), replacing wildcard-plus-credentials.
- Every error response is structured and never leaks a raw stack trace or internal path to the client (unhandled exceptions are logged server-side and returned as a generic message).
- `/api/settings` was checked to confirm it never exposes the API key itself.
- The old second Flask process (and its debug mode) no longer exists.
- Contact form validates input and fails clearly (rather than a silent unhandled exception) when SMTP isn't configured.

## 8. RAG improvements

- Real page/section-level citations with excerpts (previously filename-only).
- Document-scoped retrieval via Chroma metadata filtering (`document_id`), verified isolated per document.
- Retrieval quality pass: a distance threshold drops weak matches, and a per-document cap (only applied when searching across more than one document) prevents a handful of near-duplicate chunks from one file crowding out everything else.
- Multi-turn memory: recent conversation history is used both to rewrite ambiguous follow-ups into standalone questions before retrieval, and as context for the final answer — bounded to `MAX_HISTORY_TURNS` (default 5 exchanges), not unlimited.
- Clearer system prompt: explicit instructions to separate evidence from inference, decline to answer outside the given context, and avoid citing sources that don't support a statement.
- Sources returned to the client are the actual retrieved chunks (deterministic, code-controlled), not an LLM's self-reported citation list — a more reliable design than trusting the model to accurately say what it used.
- Everything is now configurable (chunk size/overlap, top-k, thresholds, model name) instead of hardcoded.

## 9. UI/UX improvements

- One coherent visual design (see `frontend/src/styles.css`) instead of a stock template look, with a single light/dark theme system shared by both pages (previously three incompatible implementations).
- Document dashboard replacing a marketing homepage: real upload progress (byte-level, via `XMLHttpRequest`, not a fake per-file counter), per-document status, and working actions.
- Evidence panel showing the actual excerpts behind an answer.
- Document-scope selector for asking about one file vs. all of them.
- Streaming answers appear progressively; sources appear as soon as retrieval finishes, before the answer text is done generating.
- Conversation history (switch between past conversations, delete one, export the current one).
- Both pages are valid HTML (verified with HTML Tidy) and both load correctly whether served by the backend or opened as static files.

## 10. API changes

The API surface changed meaningfully (see the full table in `README.md`);
highlights:

- `/upload/` (GET-query-string `/search/`) → `POST /api/documents` and
  `POST /api/conversations/{id}/ask` (JSON body instead of a URL query
  string — no more URL-length concerns for long questions).
- New: `DELETE /api/documents/{id}`, `/api/conversations` (create/list),
  `/api/conversations/{id}` (get/delete), `/api/conversations/{id}/ask/stream`.
- `/settings/models/` (informational-only) → `/api/settings` (reflects real, active configuration).
- `/api/contact` now lives on the same backend/port as everything else.
- Every response, success or error, is consistently structured JSON.

## 11. Database/storage changes

- Added a SQLite database (`docquery.db`) for document metadata (id,
  filename, type, size, upload time, page/chunk counts, processing status)
  and for conversations/messages — the original had neither; document
  identity was "whatever the filename is" and chat history was an
  unstructured in-memory list.
- Chroma chunks now carry `document_id`, `filename`, `chunk_id`, and
  page/section metadata, instead of just `{"source": filename}`.
- Startup no longer deletes `document_store/` or `chroma_db/` under any
  circumstance — verified via a restart-simulation test.

## 12. Testing performed

**33 automated tests, in `tests/`, run repeatedly during this build — not
just written.** They run fully offline: the real embedding model and the
real Groq API are both replaced with small deterministic fakes (see
`tests/conftest.py`), so no network access or API key is needed to run them.

What they cover, concretely:
- Upload of real PDF (generated with real text via `reportlab`), TXT, and
  DOCX (generated with real headings/paragraphs/tables via `python-docx`)
  files, and confirming each is chunked, embedded, and made searchable.
- Rejected uploads: wrong extension, oversized file, content that doesn't
  match its claimed extension, empty file.
- **The path-traversal fix**, by literally uploading a file named
  `"../../../../tmp/evil_test_file.txt"` and asserting nothing was written
  outside the storage directory.
- List, download (byte-for-byte roundtrip), delete, and delete-does-not-
  affect-other-documents.
- **Persistence across a simulated restart**: one test builds the app,
  uploads a document and asks a question, then builds a *second*, separate
  app instance pointed at the same directories (simulating a real
  stop/start) and confirms the document, its embeddings, and the
  conversation are all still there.
- **RAG grounding**: not just "an answer came back" — the test inspects
  the actual message list the fake LLM received and confirms the retrieved
  excerpt was really in it.
- Citation page numbers, document-scoped search (and that it excludes
  other documents), a deleted document disappearing from future search
  results, conversation memory across a follow-up question, conversation
  listing/auto-titling, the streaming endpoint's SSE event sequence, and
  that a streamed turn is still persisted to history afterward.
- Structured error shape across five different failure types, CORS
  behavior (allowed origin granted, untrusted origin not reflected),
  contact form validation.

Also run and verified: a full syntax check of every file, `pyflakes`
against the backend and tests (a handful of trivial unused-import/unused-
variable fixes made along the way, re-verified clean), an HTML Tidy check
of both frontend pages, and a full install of `requirements.txt`/
`requirements-dev.txt` into a clean virtual environment followed by the
entire suite passing.

**What was not verified**, and why: the real `sentence-transformers`
embedding model and the real Groq API were not exercised, because this
sandbox has no outbound network access to `huggingface.co` or Groq's API.
Everything downstream of "a vector comes back from an embedding call" was
tested with a deterministic fake standing in for both, which verifies the
pipeline thoroughly but not the real model's specific behavior. **Do one
real upload and one real question with your actual `GROQ_API_KEY` before
trusting this beyond local testing** — nothing in the architecture suggests
this would behave differently, but it genuinely wasn't run.

## 13. Remaining limitations

- No user accounts or auth — matches the original project's scope (a
  single shared workspace), not a gap introduced by this rewrite. Anyone
  who can reach the server can see/ask about/delete every document.
- No OCR for scanned PDFs — detected and reported clearly, not silently
  mishandled, but not extracted either. The loader architecture supports
  adding it later without restructuring anything.
- DOCX table-to-heading association is a reasonable approximation, not
  guaranteed exact document order (a genuine `python-docx` limitation).
- SQLite and local Chroma are appropriate for one instance / local use, as
  the "don't overengineer" brief asked for; they are not what you'd reach
  for behind a load balancer across multiple server instances.
- No rate limiting or abuse protection.
- Streaming's FastAPI/SSE plumbing is verified with a fake streaming LLM;
  real token-by-token behavior against the live Groq API specifically
  wasn't observed in this environment (see §12).

## 14. How to run the final project

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then set GROQ_API_KEY
python -m backend.main
# open http://127.0.0.1:8080
```

For tests: `pip install -r requirements-dev.txt && pytest`.

## 15. Exact environment variables

**Required:** `GROQ_API_KEY`.

**Optional** (all have working defaults — see `.env.example` for the full,
commented list): `GROQ_MODEL`, `GROQ_TEMPERATURE`, `EMBEDDING_MODEL`,
`HF_TOKEN`, `HOST`, `PORT`, `RELOAD`, `CORS_ALLOWED_ORIGINS`, `CHUNK_SIZE`,
`CHUNK_OVERLAP`, `TOP_K`, `MAX_DISTANCE_THRESHOLD`,
`MAX_CHUNKS_PER_DOCUMENT`, `MIN_MEANINGFUL_CHARS`, `MAX_HISTORY_TURNS`,
`MAX_UPLOAD_SIZE_MB`, storage path overrides, and the contact form's
`SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`RECEIVER_EMAIL`.

## 16. Final project architecture

```
backend/
├── main.py            (app factory: CORS, error handlers, static hosting, startup)
├── config.py            (every setting, from the environment)
├── database.py          (SQLite: documents, conversations, messages)
├── models/schemas.py
├── routes/               (documents, chat, contact, misc — thin, HTTP-only)
└── services/             (document_service, embedding_service, vector_store,
                            rag_service, email_service — the actual logic)
frontend/
├── index.html            (dashboard)
├── chat.html              (chat + evidence)
├── config.js
└── src/ (api.js, theme.js, components.js, styles.css)
tests/
document_store/  chroma_db/  docquery.db   (created at runtime, gitignored)
```

Routes stay thin (parse request → call a service → shape the response);
services hold the actual logic and have no FastAPI-specific code in them,
which is what made them straightforward to unit-test with fakes.

## 17. Before vs. After

| Area | Before | After |
|---|---|---|
| Upload | Dedicated upload page hardcoded the wrong port — broken as shipped; no server-side size limit; DOCX accepted by the UI, rejected by the backend | One correct shared config everywhere; server-enforced size + content-type checks; PDF/TXT/DOCX all genuinely supported |
| Persistence | Wiped on every restart | Never deleted on startup; verified to survive a simulated restart |
| RAG | Fixed k=4, no filtering, naive joined context, no conversation memory | Configurable top-k + distance threshold + diversity cap, structured context, bounded multi-turn memory with follow-up rewriting |
| Citations | Filename only, no page numbers, not deduplicated | Filename + page/section + excerpt, sourced from retrieval directly |
| Document support | PDF, TXT (crashed on non-UTF-8) | PDF, TXT (graceful fallback), DOCX (structure-aware) |
| Search | Global only | Optional per-document scoping, verified isolated |
| Chat memory | Stored but never used or read | Real, bounded multi-turn memory; conversations persisted/listable/deletable |
| Security | Verified path traversal; wildcard CORS + credentials; second server in debug mode | Path traversal fixed & verified; CORS restricted & verified; single backend |
| UI | Malformed HTML; 3 incompatible theme implementations; dead delete button; fake model selector | Valid HTML; 1 theme system; working delete; evidence panel; honest read-only settings |
| Testing | None | 37 automated tests, run and passing (see addendum below) |

## 18. Final assessment

**Portfolio quality.** This is a meaningful step past "college project" —
the architecture, error handling, test coverage, and security posture
would all hold up to real scrutiny in a portfolio or an interview
walkthrough, and the specific, verifiable fixes (not just claims) are the
kind of detail that reads as genuine engineering rather than a surface
pass.

**Not production-ready**, and I want to be specific about why, rather than
hand-wave it: there's no auth/multi-tenancy (by original design, not an
oversight, but still a real gap for "production"), no rate limiting, no
observability/monitoring, no CI pipeline, and SQLite and local Chroma won't
scale past one instance. The real embedding model and a real Groq call
have now been exercised live (see addendum), which resolves the biggest
open question from the first pass; what's still unverified is a
*successful* real generation specifically (the live run hit a dead model
name before getting that far). None of this requires architectural changes
to add later; it's just not done yet, and I'd rather say that plainly than
let "37 tests pass" imply more than it does.

---

## Addendum — fixes from a real run

Everything above was written after the sandbox-only verification pass.
This section covers what changed after the project was actually run on a
real machine with real network access, because that surfaced two things
no amount of mocked testing could have caught.

**1. The default model, `llama-3.1-8b-instant`, is dead.** Groq deprecated
it on the free/developer tier and shut it off in August 2026 (after this
project's original analysis and after my training data), so every request
failed with `model_not_found`. Fixed: `GROQ_MODEL` now defaults to
`openai/gpt-oss-20b`, Groq's own recommended replacement for that exact
model — confirmed via a fresh search, not memory. If Groq's lineup moves
again, this is a one-line `.env` change; the README's Troubleshooting
section now covers it explicitly.

**2. A bigger, structural bug: a failed LLM call crashed the streaming
connection instead of showing an error.** The real run's log showed the
`/ask/stream` endpoint return `200 OK` and then die mid-response when the
model error hit — the chat UI would have been left stuck on the "thinking"
animation forever, with nothing telling the user what went wrong. The
cause: once a `StreamingResponse`'s headers are sent (immediately, before
any content), the HTTP status can't change, so an exception that simply
propagates out of the generator has no way to surface as a clean error —
it just kills the connection. This is a real gap the mocked test suite
didn't exercise, because the fake LLM used in testing never failed.

Fixed at the source: `stream_answer()` now catches a failed retrieval or a
failed generation call *inside the generator itself* and yields a normal
`{"type": "error", "code", "message"}` event in place of `"done"` — an
in-band signal instead of a dead connection. The frontend now handles that
event type (shows the error, stops the "thinking" state). The equivalent
non-streaming path gets a matching, clean `502 LLM_REQUEST_FAILED` instead
of a generic 500. And since the (optional) follow-up-question rewriting
step makes its own LLM call before the main answer does, a failure there
specifically now degrades to using the original question rather than
failing the whole request over what's ultimately a nice-to-have.

Four new tests pin this down directly: a fake LLM that always fails
(streaming and non-streaming), a fake that fails only during question
rewriting (proving the fallback works), and the resulting connection
sequence when zero documents are uploaded at all. 37 tests pass in total.

**What the real run also confirmed, that the sandbox couldn't:** the real
`sentence-transformers/all-MiniLM-L6-v2` model downloads and loads
correctly, a real PDF/TXT/DOCX-capable upload works end to end, the
dashboard's "Ask" link correctly hands off a pre-selected document to the
chat page, and conversations persist and list correctly against real
SQLite. That's most of the pipeline this report was previously hedging on.
What's still open: a *successful* real Groq generation — worth one more
try now that the model name is fixed.

**Also fixed, smaller:** the README's install instructions assumed a
Unix shell (`source venv/bin/activate`, bare `python3`); Windows
PowerShell/cmd equivalents are now included, since that's exactly the
environment this was actually run in.
