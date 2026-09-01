const themeStorageKey = "kisa-cce-guide-theme";
const allowedThemePreferences = new Set(["system", "light", "dark", "oled"]);
const themeSelector = document.querySelector("[data-theme-selector]");
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");

const resolveTheme = (preference) => {
  if (preference === "system") {
    return systemTheme.matches ? "dark" : "light";
  }
  return preference;
};

const applyThemePreference = (preference, persist = false) => {
  if (!allowedThemePreferences.has(preference)) {
    return;
  }
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = resolveTheme(preference);
  if (themeSelector) {
    themeSelector.value = preference;
  }
  if (!persist) {
    return;
  }
  try {
    window.localStorage.setItem(themeStorageKey, preference);
  } catch {
    // Theme changes still apply when storage is unavailable.
  }
};

const initialThemePreference = document.documentElement.dataset.themePreference;
applyThemePreference(
  allowedThemePreferences.has(initialThemePreference) ? initialThemePreference : "system",
);

themeSelector?.addEventListener("change", () => {
  applyThemePreference(themeSelector.value, true);
});

systemTheme.addEventListener("change", () => {
  if (document.documentElement.dataset.themePreference === "system") {
    applyThemePreference("system");
  }
});

window.addEventListener("storage", (event) => {
  if (event.key !== themeStorageKey) {
    return;
  }
  if (event.newValue === null) {
    applyThemePreference("system");
  } else if (allowedThemePreferences.has(event.newValue)) {
    applyThemePreference(event.newValue);
  }
});

const navigationButton = document.querySelector("[data-navigation-toggle]");
const navigation = document.querySelector("[data-site-navigation]");

if (navigationButton && navigation) {
  const domainNavigation = navigation.querySelector(".site-nav__domains");
  const compactNavigation = window.matchMedia("(max-width: 768px)");
  const closeNavigation = () => {
    navigation.dataset.open = "false";
    navigationButton.setAttribute("aria-expanded", "false");
    if (domainNavigation) {
      domainNavigation.open = false;
    }
  };
  const synchronizeNavigation = (event) => {
    if (navigation.contains(document.activeElement)) {
      if (event.matches) {
        navigationButton.focus();
      } else {
        domainNavigation?.querySelector("summary")?.focus();
      }
    }
    closeNavigation();
  };

  navigation.dataset.enhanced = "true";
  navigationButton.hidden = false;
  closeNavigation();

  navigationButton.addEventListener("click", () => {
    const open = navigation.dataset.open !== "true";
    if (open) {
      navigation.dataset.open = "true";
      navigationButton.setAttribute("aria-expanded", "true");
    } else {
      closeNavigation();
    }
  });
  compactNavigation.addEventListener("change", synchronizeNavigation);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (domainNavigation?.open) {
      domainNavigation.open = false;
      domainNavigation.querySelector("summary")?.focus();
    } else if (navigation.dataset.open === "true") {
      closeNavigation();
      navigationButton.focus();
    }
  });
}

const tableOfContents = document.querySelector("[data-table-of-contents]");
const tableOfContentsToggle = document.querySelector("[data-table-of-contents-toggle]");
const tableOfContentsContent = document.querySelector("[data-table-of-contents-content]");
const tableOfContentsTitle = tableOfContents?.querySelector(".toc__title");

if (tableOfContents && tableOfContentsToggle && tableOfContentsContent && tableOfContentsTitle) {
  const compactTableOfContents = window.matchMedia("(max-width: 1080px)");
  const setTableOfContentsExpanded = (expanded) => {
    tableOfContentsContent.hidden = !expanded;
    tableOfContentsToggle.setAttribute("aria-expanded", String(expanded));
  };
  const synchronizeTableOfContents = () => {
    const compact = compactTableOfContents.matches;
    if (compact && tableOfContentsContent.contains(document.activeElement)) {
      tableOfContentsToggle.focus();
    }
    tableOfContents.dataset.enhanced = "true";
    tableOfContentsToggle.hidden = !compact;
    tableOfContentsTitle.hidden = compact;
    setTableOfContentsExpanded(!compact);
  };

  synchronizeTableOfContents();
  compactTableOfContents.addEventListener("change", synchronizeTableOfContents);
  tableOfContentsToggle.addEventListener("click", () => {
    setTableOfContentsExpanded(tableOfContentsContent.hidden);
  });
}

const copyStatus = document.querySelector("[data-copy-status]");
const clipboardAvailable =
  navigator.clipboard && typeof navigator.clipboard.writeText === "function";

for (const button of document.querySelectorAll("[data-copy-button]")) {
  if (!clipboardAvailable) {
    continue;
  }
  button.hidden = false;
  button.addEventListener("click", async () => {
    const targetIdentifier = button.getAttribute("data-copy-button");
    const code = targetIdentifier
      ? document.getElementById(targetIdentifier)
      : null;
    if (!code) {
      return;
    }
    try {
      if (copyStatus) {
        copyStatus.textContent = "";
      }
      await navigator.clipboard.writeText(code.textContent || "");
      if (copyStatus) {
        copyStatus.textContent = "코드를 복사했습니다.";
      }
    } catch {
      if (copyStatus) {
        copyStatus.textContent = "복사할 수 없습니다. 내용을 직접 선택해 주세요.";
      }
    }
  });
}

const updateCodeScrollRegion = (region) => {
  if (region.scrollWidth > region.clientWidth) {
    region.setAttribute("tabindex", "0");
  } else {
    region.removeAttribute("tabindex");
  }
};

const codeScrollRegions = document.querySelectorAll(".code-block pre");
const updateCodeScrollRegions = () => {
  for (const region of codeScrollRegions) {
    updateCodeScrollRegion(region);
  }
};

requestAnimationFrame(updateCodeScrollRegions);
window.addEventListener("resize", updateCodeScrollRegions);

if ("ResizeObserver" in window) {
  const codeResizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      updateCodeScrollRegion(entry.target);
    }
  });
  for (const region of codeScrollRegions) {
    codeResizeObserver.observe(region);
  }
}
