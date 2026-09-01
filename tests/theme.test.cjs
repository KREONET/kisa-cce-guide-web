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
