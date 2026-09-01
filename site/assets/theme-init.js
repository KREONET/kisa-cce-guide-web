(() => {
  const storageKey = "kisa-cce-guide-theme";
  const allowedPreferences = new Set(["system", "light", "dark", "oled"]);
  const root = document.documentElement;
  let preference = "system";

  try {
    const storedPreference = window.localStorage.getItem(storageKey);
    if (allowedPreferences.has(storedPreference)) {
      preference = storedPreference;
    }
  } catch {
    // Storage access can be unavailable in privacy-restricted browser contexts.
  }

  const systemUsesDarkTheme = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const resolvedTheme = preference === "system"
    ? (systemUsesDarkTheme ? "dark" : "light")
    : preference;

  root.dataset.themePreference = preference;
  root.dataset.theme = resolvedTheme;
})();
