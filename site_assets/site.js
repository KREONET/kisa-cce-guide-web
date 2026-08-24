const navigationButton = document.querySelector("[data-navigation-toggle]");
const navigation = document.querySelector("[data-site-navigation]");

if (navigationButton && navigation) {
  const closeNavigation = () => {
    navigation.dataset.open = "false";
    navigationButton.setAttribute("aria-expanded", "false");
  };

  navigation.dataset.enhanced = "true";
  navigationButton.hidden = false;
  closeNavigation();

  navigationButton.addEventListener("click", () => {
    const open = navigation.dataset.open !== "true";
    navigation.dataset.open = String(open);
    navigationButton.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigation.dataset.open === "true") {
      closeNavigation();
      navigationButton.focus();
    }
  });
}

const sidebarDisclosure = document.querySelector(".sidebar-disclosure");
if (sidebarDisclosure) {
  const desktopSidebar = window.matchMedia("(min-width: 861px)");
  const keepDesktopSidebarOpen = () => {
    if (desktopSidebar.matches) {
      sidebarDisclosure.open = true;
    }
  };
  keepDesktopSidebarOpen();
  desktopSidebar.addEventListener("change", keepDesktopSidebarOpen);
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
