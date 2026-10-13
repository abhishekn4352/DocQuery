import config from "../config.js";

const BASE = config.API_BASE_URL;

async function asJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.error?.message || `Request failed (${response.status})`;
    const error = new Error(message);
    error.code = data?.error?.code || "UNKNOWN_ERROR";
    error.status = response.status;
    throw error;
  }
  return data;
}

// --- Documents -----------------------------------------------------------

export async function listDocuments() {
  return asJson(await fetch(`${BASE}/api/documents`));
}

export async function getDocument(documentId) {
  return asJson(await fetch(`${BASE}/api/documents/${documentId}`));
}

export function downloadUrl(documentId) {
  return `${BASE}/api/documents/${documentId}/download`;
}

export async function deleteDocument(documentId) {
  return asJson(await fetch(`${BASE}/api/documents/${documentId}`, { method: "DELETE" }));
}

/**
 * Uploads with REAL byte-level progress (via XHR -- fetch() has no upload
 * progress event), not a fake per-file-count estimate.
 */
export function uploadDocument(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/api/documents`);
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else {
        const error = new Error(data?.error?.message || "Upload failed");
        error.code = data?.error?.code || "UNKNOWN_ERROR";
        reject(error);
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload."));
    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

// --- Conversations & chat --------------------------------------------------

export async function createConversation() {
  return asJson(await fetch(`${BASE}/api/conversations`, { method: "POST" }));
}

export async function listConversations() {
  return asJson(await fetch(`${BASE}/api/conversations`));
}

export async function getConversation(conversationId) {
  return asJson(await fetch(`${BASE}/api/conversations/${conversationId}`));
}

export async function deleteConversation(conversationId) {
  return asJson(await fetch(`${BASE}/api/conversations/${conversationId}`, { method: "DELETE" }));
}

export async function askQuestion(conversationId, question, documentId) {
  return asJson(
    await fetch(`${BASE}/api/conversations/${conversationId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, document_id: documentId || null }),
    })
  );
}

/**
 * Streams an answer via Server-Sent Events. `onEvent` is called with
 * {type: 'sources'|'token'|'done', ...}. Falls back to the non-streaming
 * askQuestion() automatically if the stream can't be opened at all, so a
 * flaky streaming path never blocks the user from getting an answer.
 */
export async function askQuestionStream(conversationId, question, documentId, onEvent) {
  let response;
  try {
    response = await fetch(`${BASE}/api/conversations/${conversationId}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, document_id: documentId || null }),
    });
  } catch (networkError) {
    return askQuestion(conversationId, question, documentId).then((result) => {
      onEvent({ type: "sources", sources: result.sources });
      onEvent({ type: "token", text: result.answer });
      onEvent({ type: "done", answer: result.answer, sources: result.sources });
      return result;
    });
  }

  if (!response.ok || !response.body) {
    const result = await askQuestion(conversationId, question, documentId);
    onEvent({ type: "sources", sources: result.sources });
    onEvent({ type: "token", text: result.answer });
    onEvent({ type: "done", answer: result.answer, sources: result.sources });
    return result;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const raw of events) {
      const line = raw.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice("data: ".length));
      if (event.type === "done") finalResult = event;
      onEvent(event);
    }
  }
  return finalResult;
}

// --- Contact & settings ------------------------------------------------

export async function sendContact(payload) {
  return asJson(
    await fetch(`${BASE}/api/contact`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function getSettings() {
  return asJson(await fetch(`${BASE}/api/settings`));
}
