// Shared UI helpers used by both pages. Previously duplicated (differently!)
// across index.html, upload.html, and components.js -- now there is exactly
// one implementation.

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

export function formatTimestamp(isoString) {
  try {
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

let toastContainer = null;

export function createToast(message, type = "success") {
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.className = "fixed bottom-5 right-5 z-50 flex flex-col gap-2 items-end";
    document.body.appendChild(toastContainer);
  }
  const colors = {
    success: "bg-verified text-white",
    error: "bg-danger text-white",
    info: "bg-ink text-paper dark:bg-paper dark:text-ink",
  };
  const toast = document.createElement("div");
  toast.className =
    `${colors[type] || colors.info} px-4 py-2.5 rounded-md shadow-lg text-sm font-medium ` +
    "opacity-0 translate-y-2 transition-all duration-300 ease-out max-w-xs";
  toast.textContent = message;
  toastContainer.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.remove("opacity-0", "translate-y-2");
  });
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

const STATUS_STYLES = {
  ready: { label: "Ready", classes: "bg-verified/15 text-verified" },
  processing: { label: "Processing", classes: "bg-accent/15 text-accent" },
  empty: { label: "No text found", classes: "bg-highlight/20 text-ink dark:text-paper" },
  failed: { label: "Failed", classes: "bg-danger/15 text-danger" },
};

export function statusBadgeHtml(status) {
  const style = STATUS_STYLES[status] || { label: status, classes: "bg-line/40 text-ink" };
  return `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${style.classes}">
    <span class="w-1.5 h-1.5 rounded-full bg-current"></span>${style.label}
  </span>`;
}

export function emptyStateHtml(title, subtitle) {
  return `<div class="text-center py-14 px-6">
    <p class="font-serif text-lg text-ink/70 dark:text-paper/70">${escapeHtml(title)}</p>
    <p class="text-sm text-ink/50 dark:text-paper/50 mt-1">${escapeHtml(subtitle)}</p>
  </div>`;
}

export function createLoadingSpinner(sizeClasses = "w-4 h-4") {
  const span = document.createElement("span");
  span.className = `inline-block ${sizeClasses} border-2 border-current border-t-transparent rounded-full animate-spin`;
  return span;
}
