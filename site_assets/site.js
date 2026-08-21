const navigationButton = document.querySelector("[data-navigation-toggle]");
const navigation = document.querySelector("[data-site-navigation]");

if (navigationButton && navigation) {
  const closeNavigation = () => {
    navigation.dataset.open = "false";
    navigationButton.setAttribute("aria-expanded", "false");
  };

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

const copyStatus = document.querySelector("[data-copy-status]");

for (const button of document.querySelectorAll("[data-copy-button]")) {
  button.addEventListener("click", async () => {
    const targetIdentifier = button.getAttribute("data-copy-button");
    const code = targetIdentifier
      ? document.getElementById(targetIdentifier)
      : null;
    if (!code) {
      return;
    }
    try {
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
