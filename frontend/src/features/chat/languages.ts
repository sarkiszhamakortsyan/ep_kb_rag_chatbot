// Answer languages; codes must match backend/app/rag/prompts.py LANGUAGES. "" = automatic.
export const LANGUAGES: { code: string; label: string }[] = [
  { code: "", label: "Auto" },
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "it", label: "Italiano" },
  { code: "pt", label: "Português" },
  { code: "nl", label: "Nederlands" },
  { code: "pl", label: "Polski" },
];

const KEY = "omnicorp-answer-language";

/** The chosen answer language is a per-browser preference (it may be unavailable in private mode). */
export function readLanguage(): string {
  try {
    const value = localStorage.getItem(KEY) ?? "";
    return LANGUAGES.some((l) => l.code === value) ? value : "";
  } catch {
    return "";
  }
}

export function storeLanguage(code: string) {
  try {
    localStorage.setItem(KEY, code);
  } catch {
    // Not stored: the choice lasts until the page is reloaded.
  }
}
