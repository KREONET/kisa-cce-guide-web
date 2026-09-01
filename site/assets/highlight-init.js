const highlighter = globalThis.hljs;

if (highlighter) {
  for (const code of document.querySelectorAll("code[data-highlight-language]")) {
    const language = code.getAttribute("data-highlight-language");
    if (language && highlighter.getLanguage(language)) {
      highlighter.highlightElement(code);
    }
  }
}
