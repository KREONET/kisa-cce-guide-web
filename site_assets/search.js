const searchRoot = document.querySelector("[data-search-root]");

if (searchRoot) {
  const searchInput = searchRoot.querySelector("[data-search-query]");
  const domainFilter = searchRoot.querySelector("[data-domain-filter]");
  const categoryFilter = searchRoot.querySelector("[data-category-filter]");
  const severityFilter = searchRoot.querySelector("[data-severity-filter]");
  const targetFilter = searchRoot.querySelector("[data-target-filter]");
  const status = searchRoot.querySelector("[data-search-status]");
  const resultList = searchRoot.querySelector("[data-search-results]");
  const indexUrl = searchRoot.getAttribute("data-search-index-url");

  const normalizeCode = (value) =>
    value.normalize("NFC").toLocaleLowerCase("en").replaceAll("-", "");
  const normalizeText = (value) =>
    value.normalize("NFC").toLocaleLowerCase("ko");

  const createOption = (value, label) => {
    const element = document.createElement("option");
    element.value = value;
    element.textContent = label;
    return element;
  };

  const updateQueryString = () => {
    const parameters = new URLSearchParams();
    for (const [name, element] of [
      ["q", searchInput],
      ["domain", domainFilter],
      ["category", categoryFilter],
      ["severity", severityFilter],
      ["target", targetFilter],
    ]) {
      if (element && element.value) {
        parameters.set(name, element.value);
      }
    }
    const query = parameters.toString();
    history.replaceState(null, "", query ? "?" + query : location.pathname);
  };

  const scoreRecord = (record, query) => {
    if (!query) {
      return 1;
    }
    const normalizedQuery = normalizeText(query);
    if (record.code === query) {
      return 1000;
    }
    if (normalizeCode(record.code) === normalizeCode(query)) {
      return 900;
    }
    if (record.exactTerms.includes(query)) {
      return 800;
    }
    if (
      record.exactTerms.some(
        (term) => normalizeText(term) === normalizedQuery,
      )
    ) {
      return 700;
    }
    const normalizedTitle = normalizeText(record.title);
    if (normalizedTitle === normalizedQuery) {
      return 600;
    }
    if (normalizedTitle.startsWith(normalizedQuery)) {
      return 500;
    }
    const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
    const searchableText = normalizeText(record.searchableText);
    return tokens.every((token) => searchableText.includes(token)) ? 400 : 0;
  };

  const renderResults = (records) => {
    resultList.replaceChildren();
    for (const record of records) {
      const item = document.createElement("li");
      item.className = "search-result";
      const link = document.createElement("a");
      link.href =
        searchRoot.getAttribute("data-base-path") + record.route;
      link.textContent = record.code + " " + record.title;
      const metadata = document.createElement("p");
      metadata.textContent =
        record.domainLabel +
        " · " +
        record.categoryLabel +
        " · 중요도 " +
        record.severitySourceLabel;
      const context = document.createElement("p");
      const searchableContext = record.searchableText.replace(/\s+/g, " ").trim();
      context.textContent = searchableContext.slice(0, 180);
      item.append(link, metadata, context);
      resultList.append(item);
    }
    status.textContent = records.length
      ? String(records.length) + "개 결과"
      : "일치하는 점검항목이 없습니다. 검색어나 필터를 변경해 주세요.";
  };

  const applySearch = (records) => {
    const query = searchInput.value.trim();
    const filtered = records
      .map((record) => ({record, score: scoreRecord(record, query)}))
      .filter(({record, score}) => {
        if (query && score === 0) {
          return false;
        }
        if (domainFilter.value && record.domainIdentifier !== domainFilter.value) {
          return false;
        }
        if (
          categoryFilter.value &&
          record.categoryIdentifier !== categoryFilter.value
        ) {
          return false;
        }
        if (
          severityFilter.value &&
          record.severityLevel !== severityFilter.value
        ) {
          return false;
        }
        return !(
          targetFilter.value &&
          !record.targetIdentifiers.includes(targetFilter.value)
        );
      })
      .sort(
        (left, right) =>
          right.score - left.score || left.record.order - right.record.order,
      )
      .map(({record}) => record);
    renderResults(filtered);
    updateQueryString();
  };

  fetch(indexUrl)
    .then((response) => {
      if (!response.ok) {
        throw new Error("search index request failed");
      }
      return response.json();
    })
    .then((index) => {
      const records = index.records;
      const domainOptions = new Map(
        records.map((record) => [record.domainIdentifier, record.domainLabel]),
      );
      for (const [value, label] of domainOptions) {
        domainFilter.append(createOption(value, label));
      }
      const updateCategoryOptions = (selectedValue = "") => {
        const options = new Map(
          records
            .filter(
              (record) =>
                !domainFilter.value ||
                record.domainIdentifier === domainFilter.value,
            )
            .map((record) => [
              record.categoryIdentifier,
              record.categoryLabel,
            ]),
        );
        categoryFilter.replaceChildren(createOption("", "전체"));
        for (const [value, label] of options) {
          categoryFilter.append(createOption(value, label));
        }
        categoryFilter.value = options.has(selectedValue) ? selectedValue : "";
      };
      const targetOptions = new Map();
      for (const record of records) {
        record.targetIdentifiers.forEach((identifier, targetIndex) => {
          targetOptions.set(identifier, record.targetLabels[targetIndex]);
        });
      }
      for (const [value, label] of targetOptions) {
        targetFilter.append(createOption(value, label));
      }

      const parameters = new URLSearchParams(location.search);
      searchInput.value = parameters.get("q") || "";
      domainFilter.value = parameters.get("domain") || "";
      updateCategoryOptions(parameters.get("category") || "");
      severityFilter.value = parameters.get("severity") || "";
      targetFilter.value = parameters.get("target") || "";

      for (const element of [searchInput, categoryFilter, severityFilter, targetFilter]) {
        element.addEventListener("input", () => applySearch(records));
        element.addEventListener("change", () => applySearch(records));
      }
      domainFilter.addEventListener("change", () => {
        updateCategoryOptions();
        applySearch(records);
      });
      applySearch(records);
    })
    .catch(() => {
      status.textContent = "검색 색인을 불러오지 못했습니다.";
    });
}
