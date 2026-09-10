(function () {
  const root = document.querySelector(".md-version-switcher");
  if (!root) {
    return;
  }

  const select = root.querySelector("#version-switcher");
  const current = root.querySelector(".md-version-switcher__current");
  if (!select || !current) {
    return;
  }

  const path = window.location.pathname || "/";
  const isZh = /(^|\/)zh(\/|$)/.test(path);
  const labels = isZh
    ? {
        title: "文档版本",
        current: "当前",
        stable: "正式版",
        pre: "测试版",
      }
    : {
        title: "Docs version",
        current: "Current",
        stable: "Stable",
        pre: "Pre-release",
      };

  const normalizeTarget = (baseUrl) => {
    if (!baseUrl) {
      return null;
    }

    let target = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
    if (isZh && !/(^|\/)zh\/?$/.test(target)) {
      target = `${target}zh/`;
    }
    return target;
  };

  // Build-time values from data-* attributes (fallback when runtime fetch
  // fails or versions.json is unavailable, e.g. local mkdocs serve).
  const currentChannel = root.dataset.currentChannel || "stable";
  const currentVersion = root.dataset.currentVersion || "";
  let stableVersion = root.dataset.stableVersion || "";
  const stableUrl = normalizeTarget(root.dataset.stableUrl || "/");
  let preVersion = root.dataset.preVersion || "";
  const preUrl = normalizeTarget(root.dataset.preUrl || "/pre/");
  let preAvailable =
    (root.dataset.preAvailable || "false").toLowerCase() === "true";

  // Derive the site root URL for fetching versions.json.
  //
  // The site is served under a path prefix (e.g. "/Cullinan/"), not at the
  // domain root. Fetching "/versions.json" would hit the wrong path and 404.
  // stableUrl is baked as "/Cullinan/" (see mkdocs.yml stable_url), which is
  // the site root for both stable and pre pages. Pre pages live under
  // "/Cullinan/pre/..." but share the same site root, so both channels fetch
  // the same "/Cullinan/versions.json".
  const deriveSiteRoot = () => {
    const stableUrlRaw = root.dataset.stableUrl || "";
    if (!stableUrlRaw) {
      return null;
    }
    // stableUrl is already a site-root-relative path like "/Cullinan/".
    // Ensure exactly one trailing slash, then append "versions.json".
    const base = stableUrlRaw.endsWith("/")
      ? stableUrlRaw
      : `${stableUrlRaw}/`;
    return `${base}versions.json`;
  };

  // Runtime fetch of versions.json. Overrides build-time data-* values when
  // successful; silently degrades to data-* fallback on any failure.
  const fetchVersions = async () => {
    const url = deriveSiteRoot();
    if (!url) {
      return;
    }
    try {
      // cache: "no-store" bypasses CDN caching so label updates land
      // immediately after a pre push.
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) {
        return;
      }
      const data = await resp.json();
      if (!data || typeof data !== "object") {
        return;
      }

      // Schema: { stable: { version, path }, pre: { version, path }, updated_at }
      // Only read .version; ignore path (already in data-stable-url /
      // data-pre-url) and updated_at (diagnostic only).
      const stableEntry = data.stable || {};
      const preEntry = data.pre || {};

      if (
        stableEntry &&
        typeof stableEntry.version === "string" &&
        stableEntry.version
      ) {
        stableVersion = stableEntry.version;
      }

      if (preEntry && typeof preEntry.version === "string" && preEntry.version) {
        preVersion = preEntry.version;
        // ARCH constraint 2: force preAvailable true when versions.json
        // declares a pre version, overriding the build-time value (which may
        // be "false" if stable was built before any pre existed).
        preAvailable = true;
      }
    } catch (err) {
      // Network error, JSON parse error, etc. - silently fall back to
      // build-time data-* values.
    }
  };

  const render = () => {
    const options = [];

    if (stableVersion && stableUrl) {
      options.push({
        value: stableUrl,
        label: `${labels.stable} ${stableVersion}`,
        selected: currentChannel === "stable",
      });
    }

    if (preAvailable && preVersion && preUrl) {
      options.push({
        value: preUrl,
        label: `${labels.pre} ${preVersion}`,
        selected: currentChannel === "pre",
      });
    }

    if (!options.length) {
      root.style.display = "none";
      return;
    }

    select.innerHTML = "";
    options.forEach((option) => {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      node.selected = option.selected;
      select.appendChild(node);
    });

    select.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) {
        return;
      }
      if (target.value) {
        window.location.href = target.value;
      }
    });

    const currentLabel = currentChannel === "pre" ? labels.pre : labels.stable;
    current.textContent = `${labels.current}: ${currentLabel} ${currentVersion}`.trim();
    root.setAttribute("aria-label", labels.title);
  };

  // Fetch first, then render once. Avoids double-render flicker and ensures
  // the final select state reflects runtime versions.json when available.
  fetchVersions().then(render).catch(render);
})();
