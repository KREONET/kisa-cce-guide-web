const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const repositoryRoot = path.resolve(__dirname, "..");
const initializationSource = fs.readFileSync(
  path.join(repositoryRoot, "site/assets/theme-init.js"),
  "utf8",
);
const siteSource = fs.readFileSync(
  path.join(repositoryRoot, "site/assets/site.js"),
  "utf8",
);

const createEventTarget = (initialValues = {}) => {
  const listeners = new Map();
  return {
    ...initialValues,
    addEventListener(type, listener) {
      const registered = listeners.get(type) || [];
      registered.push(listener);
      listeners.set(type, registered);
    },
    dispatch(type, event = {}) {
      for (const listener of listeners.get(type) || []) {
        listener(event);
      }
    },
    async dispatchAsync(type, event = {}) {
      for (const listener of listeners.get(type) || []) {
        await listener(event);
      }
    },
  };
};

const runInitialization = ({storedPreference = null, storageThrows = false, dark = false}) => {
  const root = {dataset: {theme: "light", themePreference: "system"}};
  const context = {
    document: {documentElement: root},
    window: {
      localStorage: {
        getItem() {
          if (storageThrows) {
            throw new Error("Storage is unavailable.");
          }
          return storedPreference;
        },
      },
      matchMedia() {
        return {matches: dark};
      },
    },
  };
  vm.runInNewContext(initializationSource, context);
  return root.dataset;
};

const runSiteBehavior = ({preference = "system", dark = false} = {}) => {
  const root = {dataset: {theme: dark ? "dark" : "light", themePreference: preference}};
  const selector = createEventTarget({value: ""});
  const systemTheme = createEventTarget({matches: dark});
  const windowTarget = createEventTarget({
    localStorage: {
      writes: [],
      setItem(key, value) {
        this.writes.push([key, value]);
      },
    },
    matchMedia() {
      return systemTheme;
    },
  });
  const document = {
    activeElement: null,
    documentElement: root,
    querySelector(selectorText) {
      return selectorText === "[data-theme-selector]" ? selector : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const context = {
    document,
    navigator: {},
    requestAnimationFrame(callback) {
      callback();
    },
    window: windowTarget,
  };
  vm.runInNewContext(siteSource, context);
  return {root, selector, systemTheme, windowTarget};
};

const runCopyBehavior = (
  {clipboardAvailable = true, copyFails = false, selectionActive = false, targetExists = true} = {},
) => {
  const attributes = new Map([["data-copy-surface", "code-target"]]);
  const control = createEventTarget({
    hidden: true,
    contains(target) {
      return target === this;
    },
  });
  const surface = createEventTarget({
    dataset: {},
    getAttribute(name) {
      return attributes.get(name) || null;
    },
    querySelector(selectorText) {
      return selectorText === "[data-copy-control]" ? control : null;
    },
  });
  const code = {textContent: "line one\n  line two\n"};
  const copyStatus = {textContent: ""};
  const clipboardWrites = [];
  const pendingTimers = new Map();
  let nextTimerIdentifier = 1;
  const systemTheme = createEventTarget({matches: false});
  const windowTarget = createEventTarget({
    localStorage: {setItem() {}},
    matchMedia() {
      return systemTheme;
    },
    getSelection() {
      return {isCollapsed: !selectionActive};
    },
    setTimeout(callback) {
      const timerIdentifier = nextTimerIdentifier;
      nextTimerIdentifier += 1;
      pendingTimers.set(timerIdentifier, callback);
      return timerIdentifier;
    },
    clearTimeout(timerIdentifier) {
      pendingTimers.delete(timerIdentifier);
    },
  });
  const document = {
    activeElement: null,
    documentElement: {dataset: {theme: "light", themePreference: "system"}},
    querySelector(selectorText) {
      if (selectorText === "[data-copy-status]") {
        return copyStatus;
      }
      return null;
    },
    querySelectorAll(selectorText) {
      return selectorText === "[data-copy-surface]" ? [surface] : [];
    },
    getElementById(identifier) {
      return targetExists && identifier === "code-target" ? code : null;
    },
    addEventListener() {},
  };
  const clipboard = clipboardAvailable
    ? {
        async writeText(value) {
          if (copyFails) {
            throw new Error("Clipboard rejected the write.");
          }
          clipboardWrites.push(value);
        },
      }
    : undefined;
  const context = {
    document,
    navigator: {clipboard},
    requestAnimationFrame(callback) {
      callback();
    },
    window: windowTarget,
  };
  vm.runInNewContext(siteSource, context);
  const flushTimers = async () => {
    const callbacks = [...pendingTimers.values()];
    pendingTimers.clear();
    for (const callback of callbacks) {
      await callback();
    }
  };
  return {clipboardWrites, code, control, copyStatus, flushTimers, surface};
};

test("theme initialization resolves system preference before styles load", () => {
  assert.deepEqual(
    {...runInitialization({dark: true})},
    {theme: "dark", themePreference: "system"},
  );
  assert.deepEqual(
    {...runInitialization({dark: false})},
    {theme: "light", themePreference: "system"},
  );
});

test("theme initialization honors explicit preferences and rejects invalid storage", () => {
  assert.deepEqual(
    {...runInitialization({storedPreference: "oled", dark: false})},
    {theme: "oled", themePreference: "oled"},
  );
  assert.deepEqual(
    {...runInitialization({storedPreference: "invalid", dark: true})},
    {theme: "dark", themePreference: "system"},
  );
  assert.deepEqual(
    {...runInitialization({storageThrows: true, dark: false})},
    {theme: "light", themePreference: "system"},
  );
});

test("theme selector persists choices and follows system changes only in system mode", () => {
  const {root, selector, systemTheme, windowTarget} = runSiteBehavior({dark: false});
  assert.equal(selector.value, "system");

  selector.value = "oled";
  selector.dispatch("change");
  assert.equal(root.dataset.theme, "oled");
  assert.equal(root.dataset.themePreference, "oled");
  assert.deepEqual(windowTarget.localStorage.writes, [
    ["kisa-cce-guide-theme", "oled"],
  ]);

  systemTheme.matches = true;
  systemTheme.dispatch("change");
  assert.equal(root.dataset.theme, "oled");

  selector.value = "system";
  selector.dispatch("change");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.dataset.themePreference, "system");

  systemTheme.matches = false;
  systemTheme.dispatch("change");
  assert.equal(root.dataset.theme, "light");
});

test("theme preference synchronizes across tabs and resets to system when removed", () => {
  const {root, selector, windowTarget} = runSiteBehavior({preference: "dark"});

  windowTarget.dispatch("storage", {
    key: "kisa-cce-guide-theme",
    newValue: "light",
  });
  assert.equal(root.dataset.theme, "light");
  assert.equal(selector.value, "light");

  windowTarget.dispatch("storage", {
    key: "kisa-cce-guide-theme",
    newValue: null,
  });
  assert.equal(root.dataset.themePreference, "system");
  assert.equal(selector.value, "system");
});

test("copy surfaces stay inactive without a usable clipboard target", () => {
  const missingClipboard = runCopyBehavior({clipboardAvailable: false});
  const missingTarget = runCopyBehavior({targetExists: false});
  assert.equal(missingClipboard.surface.dataset.copyEnabled, undefined);
  assert.equal(missingClipboard.control.hidden, true);
  assert.equal(missingTarget.surface.dataset.copyEnabled, undefined);
  assert.equal(missingTarget.control.hidden, true);
});

test("copy surfaces preserve source text and announce success", async () => {
  const {clipboardWrites, code, control, copyStatus, flushTimers, surface} = runCopyBehavior();
  assert.equal(surface.dataset.copyEnabled, "true");
  assert.equal(control.hidden, false);

  await surface.dispatchAsync("pointerdown", {clientX: 10, clientY: 10});
  await surface.dispatchAsync("click", {target: surface});
  await flushTimers();

  assert.deepEqual(clipboardWrites, [code.textContent]);
  assert.equal(copyStatus.textContent, "코드를 복사했습니다.");
  assert.equal(surface.dataset.copyState, "success");
  await flushTimers();
  assert.equal(surface.dataset.copyState, undefined);
});

test("copy surfaces do not replace intentional text selection", async () => {
  const {clipboardWrites, flushTimers, surface} = runCopyBehavior({selectionActive: true});

  await surface.dispatchAsync("click", {target: surface});
  await flushTimers();

  assert.deepEqual(clipboardWrites, []);
});

test("copy surfaces ignore pointer movement and double-click selection", async () => {
  const moved = runCopyBehavior();
  await moved.surface.dispatchAsync("pointerdown", {clientX: 0, clientY: 0});
  await moved.surface.dispatchAsync("pointermove", {clientX: 20, clientY: 0});
  await moved.surface.dispatchAsync("click", {target: moved.surface});
  await moved.flushTimers();
  assert.deepEqual(moved.clipboardWrites, []);

  const doubled = runCopyBehavior();
  await doubled.surface.dispatchAsync("click", {target: doubled.surface});
  await doubled.surface.dispatchAsync("click", {target: doubled.surface});
  await doubled.surface.dispatchAsync("dblclick");
  await doubled.flushTimers();
  assert.deepEqual(doubled.clipboardWrites, []);
});

test("native copy controls announce clipboard failures", async () => {
  const {clipboardWrites, control, copyStatus, surface} = runCopyBehavior({copyFails: true});
  let propagationStopped = false;

  await control.dispatchAsync("click", {
    stopPropagation() {
      propagationStopped = true;
    },
  });

  assert.equal(propagationStopped, true);
  assert.deepEqual(clipboardWrites, []);
  assert.equal(copyStatus.textContent, "복사할 수 없습니다. 내용을 직접 선택해 주세요.");
  assert.equal(surface.dataset.copyState, "error");
});
