// One theme implementation, shared by every page (the old project had three
// different, incompatible dark-mode implementations across its three pages).
const STORAGE_KEY = "docquery-theme";

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = saved ? saved === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", isDark);
  updateToggleButtons(isDark);
  return isDark;
}

export function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
  updateToggleButtons(isDark);
  return isDark;
}

function updateToggleButtons(isDark) {
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(isDark));
    btn.textContent = isDark ? "Light mode" : "Dark mode";
  });
}

export function wireThemeToggle(selector = "[data-theme-toggle]") {
  document.querySelectorAll(selector).forEach((btn) => {
    btn.addEventListener("click", toggleTheme);
  });
}
