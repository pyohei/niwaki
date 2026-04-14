const APP_BASE = window.__NIWAKI_BASE__ || detectBasePath(window.location.pathname);
const SIDEBAR_STORAGE_KEY = "niwaki.sidebar.collapsed";

const state = {
  route: parseRoute(window.location.pathname),
  meta: null,
  stacks: [],
  detail: null,
  detailAudit: [],
  detailError: "",
  logs: "",
  audit: [],
  aliases: [],
  system: null,
  registryStacks: [],
  gitCredential: null,
  actionOutputOverride: "",
  systemActionOutput: "",
  sidebarCollapsed: window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1",
};

function detectBasePath(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  let tailLength = 0;
  if (parts.at(-1) === "settings" || parts.at(-1) === "aliases") {
    tailLength = 1;
  } else if (parts.length >= 2 && parts.at(-2) === "stacks") {
    tailLength = 2;
  } else if (parts.at(-1) === "index.html") {
    tailLength = 1;
  } else if (pathname.endsWith("/")) {
    tailLength = 0;
  }
  const baseParts = tailLength ? parts.slice(0, -tailLength) : parts;
  return baseParts.length ? `/${baseParts.join("/")}` : "";
}

function relativePath(pathname) {
  let current = pathname;
  if (APP_BASE && current.startsWith(APP_BASE)) {
    current = current.slice(APP_BASE.length) || "/";
  }
  if (!current.startsWith("/")) {
    current = `/${current}`;
  }
  if (current !== "/" && current.endsWith("/")) {
    current = current.slice(0, -1);
  }
  return current || "/";
}

function parseRoute(pathname) {
  const current = relativePath(pathname);
  if (current === "/" || current === "/index.html") {
    return { name: "overview" };
  }
  if (current === "/settings") {
    return { name: "settings" };
  }
  if (current === "/system") {
    return { name: "system" };
  }
  if (current === "/aliases") {
    return { name: "aliases" };
  }
  const stackMatch = current.match(/^\/stacks\/([^/]+)$/);
  if (stackMatch) {
    return { name: "stack", stackId: decodeURIComponent(stackMatch[1]) };
  }
  return { name: "not-found" };
}

function appPath(path = "/") {
  let normalized = path || "/";
  if (!normalized.startsWith("/")) {
    normalized = `/${normalized}`;
  }
  if (normalized === "/") {
    return APP_BASE ? `${APP_BASE}/` : "/";
  }
  return APP_BASE ? `${APP_BASE}${normalized}` : normalized;
}

function routePath(route) {
  switch (route.name) {
    case "overview":
      return appPath("/");
    case "settings":
      return appPath("/settings");
    case "system":
      return appPath("/system");
    case "aliases":
      return appPath("/aliases");
    case "stack":
      return appPath(`/stacks/${encodeURIComponent(route.stackId)}`);
    default:
      return appPath("/");
  }
}

function apiPath(path) {
  return appPath(`/api/${String(path).replace(/^\/+/, "")}`);
}

function isInternalAppUrl(url) {
  if (url.origin !== window.location.origin) {
    return false;
  }
  return parseRoute(url.pathname).name !== "not-found";
}

const statusClass = (status) => {
  if (!status) return "badge badge-ghost";
  if (["healthy", "success", "running"].includes(status)) return "badge badge-success badge-outline";
  if (["degraded", "warn"].includes(status)) return "badge badge-warning badge-outline";
  if (["stopped", "error", "failed"].includes(status)) return "badge badge-error badge-outline";
  if (status === "empty") return "badge badge-ghost";
  return "badge badge-neutral badge-outline";
};

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] || character;
  });

async function request(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };
  const body = options.body;
  if (body && !(body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    headers,
    ...options,
  });

  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok) {
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      throw new Error(payload.error || payload.message || JSON.stringify(payload));
    }
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }

  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function handleError(error) {
  window.alert(error.message);
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return value;
  }
}

function composeFilesSummary(stack) {
  if (!stack) {
    return "-";
  }
  return stack.override_file ? `${stack.compose_file} + ${stack.override_file}` : stack.compose_file;
}

function stackRuntimeById(stackId) {
  return state.stacks.find((stack) => stack.id === stackId) || null;
}

function registryStackById(stackId) {
  return state.registryStacks.find((stack) => stack.id === stackId) || null;
}

function gitSummary(stack) {
  if (!stack?.git?.available) {
    return "git unavailable";
  }
  return `${stack.git.branch || "-"} / ${stack.git.commit || "-"}${stack.git.dirty ? " *" : ""}`;
}

function lastCommandOutput(record) {
  const steps = record?.steps || [];
  if (!steps.length) {
    return "";
  }
  const lastStep = steps[steps.length - 1];
  return lastStep.result?.output || "";
}

function metricCardMarkup(label, value, note) {
  return `
    <article class="metric-card">
      <p class="metric-label">${escapeHtml(label)}</p>
      <strong class="metric-value">${escapeHtml(value)}</strong>
      <p class="muted">${escapeHtml(note)}</p>
    </article>
  `;
}

function historyListMarkup(items, emptyText) {
  if (!items.length) {
    return `<p class="empty-state">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map(
      (item) => `
        <article class="history-item">
          <header>
            <strong class="text-sm">${escapeHtml(item.stack_name)}</strong>
            <span class="${statusClass(item.success ? "success" : "failed")}">${escapeHtml(item.action)}</span>
          </header>
          <p class="muted">${escapeHtml(formatDate(item.started_at))}</p>
          <p class="muted">${escapeHtml(`${item.success ? "success" : "failed"} · ${item.steps?.length || 0} steps`)}</p>
        </article>
      `,
    )
    .join("");
}

function containerListMarkup(containers, composeError) {
  if (!containers.length) {
    return `<p class="empty-state">${escapeHtml(composeError || "container はありません。")}</p>`;
  }
  return containers
    .map(
      (container) => `
        <article class="alias-item">
          <header>
            <strong class="text-sm">${escapeHtml(container.Name || container.Service || "container")}</strong>
            <span class="${statusClass(container.State)}">${escapeHtml(container.State || "unknown")}</span>
          </header>
          <p class="muted">${escapeHtml(container.Service || "-")}</p>
          <p class="muted">${escapeHtml(container.Status || "-")}</p>
        </article>
      `,
    )
    .join("");
}

function registryListMarkup(showOpenLink = true) {
  if (!state.registryStacks.length) {
    return '<p class="empty-state">まだ stack registry は空です。</p>';
  }
  return state.registryStacks
    .map(
      (stack) => `
        <article class="alias-item">
          <header>
            <strong class="text-sm">${escapeHtml(stack.name)}</strong>
            <span class="badge badge-neutral badge-outline">${escapeHtml(stack.id)}</span>
          </header>
          <p class="muted">${escapeHtml(`${stack.cwd} · ${composeFilesSummary(stack)}`)}</p>
          <p class="muted">${escapeHtml(stack.repo_url || "-")}</p>
          ${
            showOpenLink
              ? `<div class="inline-actions"><a class="btn btn-ghost btn-xs" href="${escapeHtml(routePath({ name: "stack", stackId: stack.id }))}">Open</a></div>`
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function stackLinksMarkup(stack) {
  const links = [
    stack?.traefik_url ? ["Traefik URL", stack.traefik_url] : null,
    stack?.repo_url ? ["Repo", stack.repo_url] : null,
  ].filter(Boolean);

  if (!links.length) {
    return '<p class="muted">stack 固有の URL はまだありません。</p>';
  }

  return `
    <div class="page-links">
      ${links
        .map(
          ([label, url]) => `
            <a class="btn btn-ghost btn-sm" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">
              ${escapeHtml(label)}
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function defaultHostnameForStack(stack) {
  const currentOverride = currentTraefikOverride(stack);
  if (currentOverride?.hostname) {
    return currentOverride.hostname;
  }
  if (!stack?.id) {
    return "app.local";
  }
  return `${String(stack.id).toLowerCase()}.local`;
}

function currentTraefikOverride(stack) {
  return stack?.current_override?.kind === "traefik" ? stack.current_override : null;
}

function currentPortOverride(stack) {
  return stack?.current_override?.kind === "port" ? stack.current_override : null;
}

function defaultTraefikPresetForStack(stack) {
  const currentOverride = currentTraefikOverride(stack);
  if (currentOverride?.preset) {
    return currentOverride.preset;
  }
  const firstService = stack?.compose_services?.[0]?.name || "";
  return String(firstService).toLowerCase() === "homepage" ? "homepage" : "generic";
}

function defaultTraefikServiceForStack(stack) {
  return currentTraefikOverride(stack)?.service_name || stack?.compose_services?.[0]?.name || "";
}

function defaultTraefikPortForStack(stack) {
  const currentOverride = currentTraefikOverride(stack);
  if (currentOverride?.target_port) {
    return currentOverride.target_port;
  }
  return stack?.compose_services?.[0]?.preferred_port || stack?.compose_services?.[0]?.ports?.[0] || "";
}

function defaultTraefikExtraEnvironment(stack) {
  return currentTraefikOverride(stack)?.extra_environment || "";
}

function defaultHomepageEnabledForStack(stack) {
  const currentOverride = currentTraefikOverride(stack);
  if (currentOverride) {
    return Boolean(currentOverride.homepage_enabled);
  }
  return true;
}

function defaultHomepageGroupForStack(stack) {
  return currentTraefikOverride(stack)?.homepage_group || "Apps";
}

function defaultHomepageCardName(stack) {
  return currentTraefikOverride(stack)?.homepage_name || stack?.name || stack?.id || "";
}

function defaultHomepageCardHref(stack) {
  const currentOverride = currentTraefikOverride(stack);
  if (currentOverride?.homepage_href) {
    return currentOverride.homepage_href;
  }
  return `http://${defaultHostnameForStack(stack)}/`;
}

function defaultHomepageIconForStack(stack) {
  return currentTraefikOverride(stack)?.homepage_icon || "";
}

function defaultHomepageDescriptionForStack(stack) {
  return currentTraefikOverride(stack)?.homepage_description || "";
}

function defaultPortOverrideServiceForStack(stack) {
  return currentPortOverride(stack)?.service_name || stack?.compose_services?.[0]?.name || "";
}

function defaultPortOverrideTargetPort(stack) {
  const currentOverride = currentPortOverride(stack);
  if (currentOverride?.target_port) {
    return currentOverride.target_port;
  }
  return stack?.compose_services?.[0]?.preferred_port || stack?.compose_services?.[0]?.ports?.[0] || "";
}

function defaultPortOverridePublishedPort(stack) {
  return currentPortOverride(stack)?.published_port || "";
}

function serviceOptionsMarkup(services, selectedName = "") {
  if (!services?.length) {
    return '<option value="">service を選べません</option>';
  }
  return services
    .map((service, index) => {
      const defaultPort = service.preferred_port || service.ports?.[0] || "";
      const selected = selectedName
        ? service.name === selectedName
        : index === 0;
      const labelSuffix = service.ports?.length ? ` (${service.ports.join(", ")})` : "";
      return `<option value="${escapeHtml(service.name)}" data-default-port="${escapeHtml(defaultPort)}" ${selected ? "selected" : ""}>${escapeHtml(service.name + labelSuffix)}</option>`;
    })
    .join("");
}

function stackFormMarkup(stack = null) {
  const current = stack || {};
  const editing = Boolean(stack);
  return `
    <form id="stack-form" class="settings-form">
      <input id="stack-id-input" name="id" type="hidden" value="${escapeHtml(current.id || "")}" />
      <label>
        Name
        <input class="input input-sm input-bordered w-full" id="stack-name-input" name="name" placeholder="Homepage" value="${escapeHtml(current.name || "")}" required />
      </label>
      <label class="settings-form-wide">
        Repo URL
        <input class="input input-sm input-bordered w-full" id="stack-repo-url-input" name="repo_url" placeholder="https://github.com/example/repo.git" value="${escapeHtml(current.repo_url || "")}" />
      </label>
      <label>
        Compose File
        <input class="input input-sm input-bordered w-full" id="stack-compose-input" name="compose_file" placeholder="compose.homepage.yaml" value="${escapeHtml(current.compose_file || "compose.yaml")}" required />
      </label>
      <label>
        Branch
        <input class="input input-sm input-bordered w-full" id="stack-branch-input" name="branch" placeholder="main" value="${escapeHtml(current.branch || "")}" />
      </label>
      <div class="detail-meta settings-form-wide">
        ${
          editing
            ? `
              <span>ID: <code>${escapeHtml(current.id || "-")}</code></span>
              <span>CWD: <code>${escapeHtml(current.cwd || "-")}</code></span>
              <span>Override: <code>${escapeHtml(current.override_file || "-")}</code></span>
            `
            : `
              <span>ID は Name から自動生成します</span>
              <span>CWD は Stack Root 配下に自動作成されます</span>
              <span>Override File は自動生成されます</span>
            `
        }
      </div>
      <label class="settings-form-wide">
        Notes
        <textarea class="textarea textarea-sm textarea-bordered min-h-20 w-full" id="stack-notes-input" name="notes" placeholder="optional notes">${escapeHtml(current.notes || "")}</textarea>
      </label>
      <div class="inline-actions settings-form-wide">
        <button class="btn btn-sm btn-primary" type="submit">${editing ? "Save Stack" : "Create Stack"}</button>
        <button class="btn btn-sm btn-ghost" type="reset">${editing ? "Reset" : "Clear"}</button>
        ${editing ? '<button class="btn btn-sm btn-error" id="stack-delete" type="button">Delete Stack</button>' : ""}
      </div>
    </form>
  `;
}

function renderAccessCards() {
  const root = document.getElementById("access-cards");
  if (!state.meta) {
    root.innerHTML = "";
    return;
  }
  const cards = [
    ["Primary", state.meta.base_url],
  ].filter(Boolean);

  root.innerHTML = cards
    .map(
      ([label, url]) => `
        <article class="access-card">
          <p class="eyebrow">${escapeHtml(label)}</p>
          <a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>
        </article>
      `,
    )
    .join("");
}

function renderMainNav() {
  const root = document.getElementById("main-nav");
  const items = [
    { name: "overview", label: "Overview" },
    { name: "system", label: "System" },
    { name: "settings", label: "Settings" },
    state.meta?.mdns_enabled ? { name: "aliases", label: "mDNS" } : null,
  ].filter(Boolean);

  root.innerHTML = items
    .map((item) => {
      const active = state.route.name === item.name;
      return `
        <a class="btn btn-sm ${active ? "btn-primary" : "btn-ghost"}" href="${escapeHtml(routePath({ name: item.name }))}">
          ${escapeHtml(item.label)}
        </a>
      `;
    })
    .join("");
}

function renderStackSidebar() {
  const root = document.getElementById("stack-list");
  if (!state.stacks.length) {
    root.innerHTML = '<p class="empty-state">stack はまだありません。Overview から追加してください。</p>';
    return;
  }
  root.innerHTML = state.stacks
    .map((stack) => {
      const selected = state.route.name === "stack" && state.route.stackId === stack.id ? "selected" : "";
      return `
        <a class="stack-item ${selected}" href="${escapeHtml(routePath({ name: "stack", stackId: stack.id }))}">
          <header>
            <strong class="text-base stack-name">${escapeHtml(stack.name)}</strong>
            <span class="${statusClass(stack.status)}">${escapeHtml(stack.status)}</span>
          </header>
        </a>
      `;
    })
    .join("");
}

function renderShellState() {
  const shell = document.getElementById("shell");
  const toggle = document.getElementById("sidebar-toggle");
  const hideSidebar = state.route.name === "settings" || state.route.name === "system";
  if (shell) {
    shell.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
    shell.classList.toggle("sidebar-hidden", hideSidebar);
  }
  if (toggle) {
    toggle.textContent = state.sidebarCollapsed ? "Expand" : "Collapse";
    toggle.setAttribute("aria-pressed", state.sidebarCollapsed ? "true" : "false");
    toggle.hidden = hideSidebar;
  }
}

function renderShellOnly() {
  state.route = parseRoute(window.location.pathname);
  renderShellState();
  renderMainNav();
  renderStackSidebar();
}

function renderOverviewPage() {
  const root = document.getElementById("page-content");
  const healthyCount = state.stacks.filter((stack) => stack.status === "healthy").length;
  const attentionCount = state.stacks.filter((stack) => ["degraded", "error", "stopped"].includes(stack.status)).length;
  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">Overview</p>
        <h2 class="page-title">Stack ごとの管理画面</h2>
        <p class="page-copy">Overview では全体の状況確認と新規 stack 登録だけを扱います。各 stack の操作と設定変更は個別ページに寄せます。</p>
      </div>
    </section>

    <section class="summary-grid">
      ${metricCardMarkup("Registered", String(state.stacks.length), "registry にある stack 数")}
      ${metricCardMarkup("Healthy", String(healthyCount), "正常に動作している stack")}
      ${metricCardMarkup("Attention", String(attentionCount), "確認が必要な stack")}
      ${metricCardMarkup("Git Credential", state.gitCredential ? "configured" : "missing", state.gitCredential?.username || "Settings から設定")}
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Register Stack</h2>
        </div>
        ${stackFormMarkup()}
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Recent Deploys</h2>
        </div>
        <div class="history-list">${historyListMarkup(state.audit, "まだ実行履歴はありません。")}</div>
      </section>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2 class="text-lg font-semibold">Registered Stacks</h2>
      </div>
      <div class="alias-list">${registryListMarkup(true)}</div>
    </section>
  `;

  bindStackForm({ redirectToSavedStack: true });
}

function renderStackPage() {
  const root = document.getElementById("page-content");
  if (state.detailError) {
    root.innerHTML = `
      <section class="page-header">
        <div>
          <p class="eyebrow">Stack</p>
          <h2 class="page-title">Stack not found</h2>
          <p class="page-copy">${escapeHtml(state.detailError)}</p>
        </div>
      </section>
      <section class="panel">
        <p class="empty-state">stack が見つからないため詳細を表示できません。Overview に戻って registry を確認してください。</p>
        <div class="inline-actions">
          <a class="btn btn-sm btn-primary" href="${escapeHtml(routePath({ name: "overview" }))}">Back to Overview</a>
        </div>
      </section>
    `;
    return;
  }

  if (!state.detail) {
    root.innerHTML = '<p class="empty-state">Stack を読み込めませんでした。</p>';
    return;
  }

  const registryStack = registryStackById(state.detail.id) || state.detail;
  const commandOutput = state.actionOutputOverride || lastCommandOutput(state.detail.last_action) || "まだ実行履歴はありません。";
  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">Stack</p>
        <div class="title-row">
          <h2 class="page-title">${escapeHtml(state.detail.name)}</h2>
          <span class="${statusClass(state.detail.status)}">${escapeHtml(state.detail.status)}</span>
        </div>
        <p class="page-copy">${escapeHtml(state.detail.cwd)}</p>
      </div>
      ${stackLinksMarkup(state.detail)}
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Operations</h2>
        </div>
        <div class="detail-meta">
          <span>CWD: <code>${escapeHtml(state.detail.cwd)}</code></span>
          <span>Repo: <code>${escapeHtml(state.detail.repo_url || "-")}</code></span>
          <span>Compose: <code>${escapeHtml(state.detail.compose_file)}</code></span>
          <span>Override: <code>${escapeHtml(state.detail.override_file || "-")}</code></span>
          <span>Git: ${escapeHtml(gitSummary(state.detail))}</span>
          <span>Last Action: ${escapeHtml(state.detail.last_action ? `${state.detail.last_action.action} (${state.detail.last_action.success ? "success" : "failed"})` : "none")}</span>
        </div>
        <div class="actions" id="stack-actions">
          ${[
            ["clone", "Clone", false],
            ["git-pull", "Git Pull", false],
            ["validate", "Validate", false],
            ["pull", "Compose Pull", false],
            ["up", "Up -d", false],
            ["restart", "Restart", false],
            ["down", "Down", true],
            ["deploy", "Deploy", false],
          ]
            .map(
              ([action, label, danger]) =>
                `<button class="btn btn-sm ${danger ? "btn-error" : "btn-primary"}" type="button" data-action="${action}" data-danger="${danger ? "true" : "false"}">${escapeHtml(label)}</button>`,
            )
            .join("")}
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Stack Settings</h2>
        </div>
        ${stackFormMarkup(registryStack)}
      </section>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Containers</h2>
        </div>
        <div class="list-block">${containerListMarkup(state.detail.containers || [], state.detail.compose_error)}</div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Deploy History</h2>
        </div>
        <div class="history-list">${historyListMarkup(state.detailAudit, "この stack の実行履歴はまだありません。")}</div>
      </section>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Logs</h2>
        </div>
        <pre class="code-block" id="log-output">${escapeHtml(state.logs || "log がありません。")}</pre>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Last Command</h2>
        </div>
        <pre class="code-block" id="action-output">${escapeHtml(commandOutput)}</pre>
      </section>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Traefik Override</h2>
        </div>
        ${
          state.detail.compose_services_error
            ? `<p class="empty-state">${escapeHtml(state.detail.compose_services_error)}</p>`
            : `
              <form id="traefik-override-form" class="settings-form">
                <label>
                  Service
                  <select class="select select-sm select-bordered w-full" id="traefik-service-input" name="service_name">
                    ${serviceOptionsMarkup(state.detail.compose_services || [], defaultTraefikServiceForStack(state.detail))}
                  </select>
                </label>
                <label>
                  Preset
                  <select class="select select-sm select-bordered w-full" id="traefik-preset-input" name="preset">
                    <option value="generic" ${defaultTraefikPresetForStack(state.detail) === "generic" ? "selected" : ""}>Generic</option>
                    <option value="homepage" ${defaultTraefikPresetForStack(state.detail) === "homepage" ? "selected" : ""}>Homepage</option>
                  </select>
                </label>
                <label>
                  Internal Port
                  <input class="input input-sm input-bordered w-full" id="traefik-port-input" name="target_port" value="${escapeHtml(defaultTraefikPortForStack(state.detail))}" placeholder="3000" required />
                </label>
                <label>
                  Hostname
                  <input class="input input-sm input-bordered w-full" id="traefik-hostname-input" name="hostname" value="${escapeHtml(defaultHostnameForStack(state.detail))}" placeholder="genkan.local" required />
                </label>
                ${
                  state.meta?.mdns_enabled
                    ? `
                      <label class="label cursor-pointer justify-start gap-2">
                        <input class="checkbox checkbox-sm" id="traefik-create-alias-input" name="create_alias" type="checkbox" checked />
                        <span class="label-text">mDNS alias も作成する</span>
                      </label>
                    `
                    : ""
                }
                <label class="settings-form-wide">
                  Extra Environment
                  <textarea class="textarea textarea-sm textarea-bordered min-h-20 w-full" id="traefik-extra-environment-input" name="extra_environment" placeholder="KEY=value&#10;ANOTHER_KEY=value">${escapeHtml(defaultTraefikExtraEnvironment(state.detail))}</textarea>
                </label>
                <label class="label cursor-pointer justify-start gap-2 settings-form-wide">
                  <input class="checkbox checkbox-sm" id="homepage-enabled-input" name="homepage_enabled" type="checkbox" ${defaultHomepageEnabledForStack(state.detail) ? "checked" : ""} />
                  <span class="label-text">Homepage listing labels も付ける</span>
                </label>
                <label>
                  Homepage Group
                  <input class="input input-sm input-bordered w-full" id="homepage-group-input" name="homepage_group" value="${escapeHtml(defaultHomepageGroupForStack(state.detail))}" placeholder="Apps" />
                </label>
                <label>
                  Homepage Name
                  <input class="input input-sm input-bordered w-full" id="homepage-name-input" name="homepage_name" value="${escapeHtml(defaultHomepageCardName(state.detail))}" placeholder="Uptime Kuma" />
                </label>
                <label>
                  Homepage Icon
                  <input class="input input-sm input-bordered w-full" id="homepage-icon-input" name="homepage_icon" value="${escapeHtml(defaultHomepageIconForStack(state.detail))}" placeholder="mdi-monitor-dashboard" />
                </label>
                <label>
                  Homepage Href
                  <input class="input input-sm input-bordered w-full" id="homepage-href-input" name="homepage_href" value="${escapeHtml(defaultHomepageCardHref(state.detail))}" placeholder="http://genkan.local/" />
                </label>
                <label class="settings-form-wide">
                  Homepage Description
                  <input class="input input-sm input-bordered w-full" id="homepage-description-input" name="homepage_description" value="${escapeHtml(defaultHomepageDescriptionForStack(state.detail))}" placeholder="Main app" />
                </label>
                <p class="muted settings-form-wide">実行すると <code>down</code> → override 再作成 → <code>up -d</code> を順番に行います。Homepage preset を選ぶと <code>HOMEPAGE_ALLOWED_HOSTS</code> を自動で入れます。</p>
                <div class="inline-actions settings-form-wide">
                  <button class="btn btn-sm btn-primary" type="submit">Down + Recreate + Up -d</button>
                </div>
              </form>
            `
        }
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Port Override</h2>
        </div>
        ${
          state.detail.compose_services_error
            ? `<p class="empty-state">${escapeHtml(state.detail.compose_services_error)}</p>`
            : `
              <form id="port-override-form" class="settings-form">
                <p class="muted">override file を上書きして、service を host port に直接 publish します。Traefik Override とは併用ではなく切り替え前提で、<code>down</code> → override 再作成 → <code>up -d</code> を実行します。</p>
                <label>
                  Service
                  <select class="select select-sm select-bordered w-full" id="port-override-service-input" name="service_name">
                    ${serviceOptionsMarkup(state.detail.compose_services || [], defaultPortOverrideServiceForStack(state.detail))}
                  </select>
                </label>
                <label>
                  Internal Port
                  <input class="input input-sm input-bordered w-full" id="port-override-target-port-input" name="target_port" value="${escapeHtml(defaultPortOverrideTargetPort(state.detail))}" placeholder="3000" required />
                </label>
                <label>
                  Published Port
                  <input class="input input-sm input-bordered w-full" id="port-override-published-port-input" name="published_port" value="${escapeHtml(defaultPortOverridePublishedPort(state.detail))}" placeholder="8081" required />
                </label>
                <div class="inline-actions settings-form-wide">
                  <button class="btn btn-sm btn-secondary" type="submit">Down + Recreate + Up -d</button>
                </div>
              </form>
            `
        }
      </section>
    </section>
  `;

  bindStackActions();
  bindStackForm({ redirectToSavedStack: false });
  bindStackDelete();
  bindTraefikOverrideForm();
  bindPortOverrideForm();
}

function renderSettingsPage() {
  const root = document.getElementById("page-content");
  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">System</p>
        <h2 class="page-title">Settings</h2>
        <p class="page-copy">システム共通の Git credential を保持します。stack ごとの credential 管理はしません。</p>
      </div>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Git Credential</h2>
        </div>
        <form id="credential-form" class="settings-form">
          <label>
            Username
            <input class="input input-sm input-bordered w-full" id="credential-username-input" name="username" placeholder="git username" value="${escapeHtml(state.gitCredential?.username || "")}" required />
          </label>
          <label>
            Password / Token
            <input class="input input-sm input-bordered w-full" id="credential-secret-input" name="secret" placeholder="leave blank to keep existing value" type="password" />
          </label>
          <div class="inline-actions settings-form-wide">
            <button class="btn btn-sm btn-primary" type="submit">Save Credential</button>
            <button class="btn btn-sm btn-ghost" id="credential-form-clear" type="reset">Clear</button>
            <button class="btn btn-sm btn-error" id="credential-delete" type="button">Delete</button>
          </div>
        </form>
        <div id="credential-status" class="alias-list">
          ${
            state.gitCredential?.has_secret
              ? `
                <article class="alias-item">
                  <header>
                    <strong class="text-sm">System Credential</strong>
                    <span class="badge badge-neutral badge-outline">${escapeHtml(state.gitCredential.username)}</span>
                  </header>
                  <p class="muted">secret saved</p>
                  <p class="muted">${escapeHtml(state.gitCredential.updated_at || "")}</p>
                </article>
              `
              : '<p class="empty-state">まだ Git credential はありません。</p>'
          }
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Runtime</h2>
        </div>
        <div class="detail-meta">
          <span>Primary URL: <code>${escapeHtml(state.meta?.base_url || "-")}</code></span>
          <span>Settings DB: <code>${escapeHtml(state.meta?.settings_db_path || "-")}</code></span>
          <span>Stack Root: <code>${escapeHtml(state.meta?.stack_root || "-")}</code></span>
          <span>mDNS Enabled: <code>${escapeHtml(state.meta?.mdns_enabled ? "true" : "false")}</code></span>
        </div>
      </section>
    </section>
  `;

  bindCredentialForm();
}

function renderSystemPage() {
  const root = document.getElementById("page-content");
  const jobs = state.system?.jobs || [];
  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">System</p>
        <h2 class="page-title">Niwaki Runtime</h2>
        <p class="page-copy">Niwaki 自身の更新と再起動を扱います。必要なら登録済み stack も順番に deploy してから runtime を更新します。</p>
      </div>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Operations</h2>
        </div>
        <form id="system-action-form" class="settings-form">
          <label>
            Action
            <select class="select select-sm select-bordered w-full" id="system-action-input" name="action">
              <option value="restart">Restart Niwaki</option>
              <option value="update">Update Niwaki</option>
            </select>
          </label>
          <label class="label cursor-pointer justify-start gap-2 settings-form-wide">
            <input class="checkbox checkbox-sm" id="system-rolling-update-input" name="rolling_update" type="checkbox" checked />
            <span class="label-text">登録済み stack も rolling update する</span>
          </label>
          <p class="muted settings-form-wide">実行は detached job に逃がすので、Niwaki 自身の再起動中でもジョブは継続します。stack 更新は registry 順に <code>git pull</code> / <code>compose pull</code> / <code>up -d</code> を実行します。</p>
          <div class="inline-actions settings-form-wide">
            <button class="btn btn-sm btn-primary" type="submit">Run System Action</button>
          </div>
        </form>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Runtime</h2>
        </div>
        <div class="detail-meta">
          <span>Primary URL: <code>${escapeHtml(state.meta?.base_url || "-")}</code></span>
          <span>Runtime Root: <code>${escapeHtml(state.system?.runtime_root || state.meta?.runtime_root || "-")}</code></span>
          <span>Stack Root: <code>${escapeHtml(state.system?.stack_root || state.meta?.stack_root || "-")}</code></span>
          <span>Compose File: <code>${escapeHtml(state.system?.compose_file || "-")}</code></span>
          <span>Available: <code>${escapeHtml(state.system?.available ? "true" : "false")}</code></span>
        </div>
      </section>
    </section>

    <section class="page-grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Active Jobs</h2>
        </div>
        <div class="history-list">
          ${
            jobs.length
              ? jobs
                  .map(
                    (job) => `
                      <article class="history-item">
                        <header>
                          <strong class="text-sm">${escapeHtml(job.name)}</strong>
                          <span class="${statusClass(job.state)}">${escapeHtml(job.state || "unknown")}</span>
                        </header>
                        <p class="muted">${escapeHtml(job.action || "-")}</p>
                        <p class="muted">${escapeHtml(job.status || "-")}</p>
                      </article>
                    `,
                  )
                  .join("")
              : '<p class="empty-state">現在動いている system job はありません。</p>'
          }
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2 class="text-lg font-semibold">Last Command</h2>
        </div>
        <pre class="code-block">${escapeHtml(state.systemActionOutput || "まだ実行していません。")}</pre>
      </section>
    </section>
  `;

  bindSystemActionForm();
}

function renderAliasesPage() {
  const root = document.getElementById("page-content");
  if (!state.meta?.mdns_enabled) {
    root.innerHTML = `
      <section class="page-header">
        <div>
          <p class="eyebrow">Network</p>
          <h2 class="page-title">mDNS Aliases</h2>
          <p class="page-copy">mDNS はこの環境で無効です。</p>
        </div>
      </section>
      <section class="panel">
        <p class="empty-state">mDNS feature が無効なため alias を管理できません。</p>
      </section>
    `;
    return;
  }

  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">Network</p>
        <h2 class="page-title">mDNS Aliases</h2>
        <p class="page-copy">mDNS alias は stack 単位ではなくホスト全体の導線なので、独立した infra ページに分けています。</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2 class="text-lg font-semibold">Alias Registry</h2>
        <span class="badge badge-neutral badge-outline">${escapeHtml(state.meta.mdns_target_ip || "target ip unset")}</span>
      </div>
      <form id="alias-form" class="alias-form">
        <label>
          Alias
          <input class="input input-sm input-bordered w-full" id="alias-input" name="alias" placeholder="niwaki.local" required />
        </label>
        <label>
          Target IP
          <input class="input input-sm input-bordered w-full" id="target-ip-input" name="target_ip" value="${escapeHtml(state.meta.mdns_target_ip || "")}" placeholder="192.168.1.10" />
        </label>
        <button class="btn btn-sm btn-primary self-end" type="submit">Create Alias</button>
      </form>
      <div id="alias-list" class="alias-list">
        ${
          state.aliases.length
            ? state.aliases
                .map(
                  (alias) => `
                    <article class="alias-item">
                      <header>
                        <strong class="text-sm">${escapeHtml(alias.alias)}</strong>
                        <span class="${statusClass(alias.state)}">${escapeHtml(alias.state || "unknown")}</span>
                      </header>
                      <p class="muted">${escapeHtml(alias.target_ip || "-")}</p>
                      <p class="muted">${escapeHtml(alias.status || "-")}</p>
                      <div class="inline-actions">
                        <button class="btn btn-ghost btn-xs" type="button" data-delete-alias="${escapeHtml(alias.alias)}">Delete</button>
                      </div>
                    </article>
                  `,
                )
                .join("")
            : '<p class="empty-state">まだ alias はありません。</p>'
        }
      </div>
    </section>
  `;

  bindAliasForm();
}

function renderNotFoundPage() {
  const root = document.getElementById("page-content");
  root.innerHTML = `
    <section class="page-header">
      <div>
        <p class="eyebrow">Not Found</p>
        <h2 class="page-title">このページはありません</h2>
      </div>
    </section>
    <section class="panel">
      <p class="empty-state">URL を確認してください。</p>
      <div class="inline-actions">
        <a class="btn btn-sm btn-primary" href="${escapeHtml(routePath({ name: "overview" }))}">Back to Overview</a>
      </div>
    </section>
  `;
}

function render() {
  renderShellState();
  renderAccessCards();
  renderMainNav();
  renderStackSidebar();

  switch (state.route.name) {
    case "overview":
      renderOverviewPage();
      break;
    case "stack":
      renderStackPage();
      break;
    case "settings":
      renderSettingsPage();
      break;
    case "system":
      renderSystemPage();
      break;
    case "aliases":
      renderAliasesPage();
      break;
    default:
      renderNotFoundPage();
      break;
  }
}

function stackFormPayload() {
  return {
    id: document.getElementById("stack-id-input").value,
    name: document.getElementById("stack-name-input").value,
    repo_url: document.getElementById("stack-repo-url-input").value,
    compose_file: document.getElementById("stack-compose-input").value,
    branch: document.getElementById("stack-branch-input").value,
    notes: document.getElementById("stack-notes-input").value,
  };
}

function bindStackForm({ redirectToSavedStack }) {
  const form = document.getElementById("stack-form");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    try {
      event.preventDefault();
      const saved = await request(apiPath("settings/stacks"), {
        method: "POST",
        body: JSON.stringify(stackFormPayload()),
      });
      state.actionOutputOverride = "";
      if (redirectToSavedStack) {
        window.location.href = routePath({ name: "stack", stackId: saved.id });
        return;
      }
      await loadCurrentPage();
      render();
    } catch (error) {
      handleError(error);
    }
  });
}

function bindStackDelete() {
  const button = document.getElementById("stack-delete");
  if (!button || !state.detail) {
    return;
  }
  button.addEventListener("click", async () => {
    try {
      if (!window.confirm(`${state.detail.id} を registry から削除しますか？`)) {
        return;
      }
      await request(apiPath(`settings/stacks/${encodeURIComponent(state.detail.id)}`), { method: "DELETE" });
      window.location.href = routePath({ name: "overview" });
    } catch (error) {
      handleError(error);
    }
  });
}

function bindStackActions() {
  document.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const action = button.dataset.action;
        if (button.dataset.danger === "true" && !window.confirm(`${state.detail.name} に ${action} を実行しますか？`)) {
          return;
        }
        const record = await request(apiPath(`stacks/${encodeURIComponent(state.detail.id)}/actions/${action}`), {
          method: "POST",
        });
        state.actionOutputOverride = JSON.stringify(record, null, 2);
        await loadCurrentPage();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  });
}

function bindTraefikOverrideForm() {
  const form = document.getElementById("traefik-override-form");
  if (!form || !state.detail) {
    return;
  }
  const serviceInput = document.getElementById("traefik-service-input");
  const presetInput = document.getElementById("traefik-preset-input");
  const portInput = document.getElementById("traefik-port-input");
  const hostnameInput = document.getElementById("traefik-hostname-input");
  const homepageHrefInput = document.getElementById("homepage-href-input");

  if (serviceInput && portInput) {
    serviceInput.addEventListener("change", () => {
      const option = serviceInput.selectedOptions?.[0];
      const defaultPort = option?.dataset.defaultPort || "";
      if (defaultPort) {
        portInput.value = defaultPort;
      }
      if (presetInput) {
        presetInput.value = serviceInput.value === "homepage" ? "homepage" : "generic";
      }
    });
  }

  if (hostnameInput && homepageHrefInput) {
    hostnameInput.addEventListener("change", () => {
      if (!homepageHrefInput.value || homepageHrefInput.value === defaultHomepageCardHref(state.detail)) {
        homepageHrefInput.value = `http://${hostnameInput.value.replace(/\/+$/, "")}/`;
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    try {
      event.preventDefault();
      const payload = {
        service_name: document.getElementById("traefik-service-input").value,
        preset: document.getElementById("traefik-preset-input").value,
        target_port: document.getElementById("traefik-port-input").value,
        hostname: document.getElementById("traefik-hostname-input").value,
        create_alias: Boolean(document.getElementById("traefik-create-alias-input")?.checked),
        extra_environment: document.getElementById("traefik-extra-environment-input").value,
        homepage_enabled: Boolean(document.getElementById("homepage-enabled-input")?.checked),
        homepage_group: document.getElementById("homepage-group-input").value,
        homepage_name: document.getElementById("homepage-name-input").value,
        homepage_icon: document.getElementById("homepage-icon-input").value,
        homepage_href: document.getElementById("homepage-href-input").value,
        homepage_description: document.getElementById("homepage-description-input").value,
      };
      const result = await request(apiPath(`stacks/${encodeURIComponent(state.detail.id)}/override/traefik`), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.actionOutputOverride = JSON.stringify(result, null, 2);
      await loadCurrentPage();
      render();
    } catch (error) {
      handleError(error);
    }
  });
}

function bindPortOverrideForm() {
  const form = document.getElementById("port-override-form");
  if (!form || !state.detail) {
    return;
  }
  const serviceInput = document.getElementById("port-override-service-input");
  const targetPortInput = document.getElementById("port-override-target-port-input");

  if (serviceInput && targetPortInput) {
    serviceInput.addEventListener("change", () => {
      const option = serviceInput.selectedOptions?.[0];
      const defaultPort = option?.dataset.defaultPort || "";
      if (defaultPort) {
        targetPortInput.value = defaultPort;
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    try {
      event.preventDefault();
      const result = await request(apiPath(`stacks/${encodeURIComponent(state.detail.id)}/override/port`), {
        method: "POST",
        body: JSON.stringify({
          service_name: document.getElementById("port-override-service-input").value,
          target_port: document.getElementById("port-override-target-port-input").value,
          published_port: document.getElementById("port-override-published-port-input").value,
        }),
      });
      state.actionOutputOverride = JSON.stringify(result, null, 2);
      await loadCurrentPage();
      render();
    } catch (error) {
      handleError(error);
    }
  });
}

function bindCredentialForm() {
  const form = document.getElementById("credential-form");
  const deleteButton = document.getElementById("credential-delete");
  if (form) {
    form.addEventListener("submit", async (event) => {
      try {
        event.preventDefault();
        await request(apiPath("settings/git-credential"), {
          method: "POST",
          body: JSON.stringify({
            username: document.getElementById("credential-username-input").value,
            secret: document.getElementById("credential-secret-input").value,
          }),
        });
        await loadCurrentPage();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  }
  if (deleteButton) {
    deleteButton.addEventListener("click", async () => {
      try {
        if (!window.confirm("システムの Git credential を削除しますか？")) {
          return;
        }
        await request(apiPath("settings/git-credential"), { method: "DELETE" });
        await loadCurrentPage();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  }
}

function bindSystemActionForm() {
  const form = document.getElementById("system-action-form");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    try {
      event.preventDefault();
      const action = document.getElementById("system-action-input").value;
      const rollingUpdate = Boolean(document.getElementById("system-rolling-update-input")?.checked);
      if (!window.confirm(`system action ${action} を実行しますか？`)) {
        return;
      }
      const result = await request(apiPath(`system/actions/${encodeURIComponent(action)}`), {
        method: "POST",
        body: JSON.stringify({
          rolling_update: rollingUpdate,
        }),
      });
      state.systemActionOutput = JSON.stringify(result, null, 2);
      state.system = await request(apiPath("system"));
      render();
    } catch (error) {
      handleError(error);
    }
  });
}

function bindAliasForm() {
  const form = document.getElementById("alias-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      try {
        event.preventDefault();
        await request(apiPath("mdns/aliases"), {
          method: "POST",
          body: JSON.stringify({
            alias: document.getElementById("alias-input").value,
            target_ip: document.getElementById("target-ip-input").value,
          }),
        });
        await loadCurrentPage();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  }

  document.querySelectorAll("button[data-delete-alias]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const alias = button.dataset.deleteAlias;
        if (!window.confirm(`${alias} を削除しますか？`)) {
          return;
        }
        await request(apiPath(`mdns/aliases/${encodeURIComponent(alias)}`), { method: "DELETE" });
        await loadCurrentPage();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  });
}

async function loadCurrentPage() {
  const previousRoute = state.route;
  state.route = parseRoute(window.location.pathname);
  if (
    state.route.name !== "stack" ||
    previousRoute?.name !== "stack" ||
    previousRoute.stackId !== state.route.stackId
  ) {
    state.actionOutputOverride = "";
  }
  if (state.route.name !== "system") {
    state.systemActionOutput = "";
  }
  state.detail = null;
  state.detailAudit = [];
  state.detailError = "";
  state.logs = "";
  state.aliases = [];
  state.system = null;

  state.meta = await request(apiPath("meta"));

  const tasks = [
    request(apiPath("stacks")),
    request(apiPath("settings/stacks")),
    request(apiPath("settings/git-credential")),
    state.route.name === "overview" ? request(apiPath("audit?limit=12")) : Promise.resolve({ items: [] }),
  ];
  const [stacksResponse, registryResponse, credentialResponse, auditResponse] = await Promise.all(tasks);

  state.stacks = stacksResponse.items || [];
  state.registryStacks = registryResponse.items || [];
  state.gitCredential = credentialResponse?.has_secret ? credentialResponse : null;
  state.audit = auditResponse.items || [];

  if (state.route.name === "system") {
    state.system = await request(apiPath("system"));
  }

  if (state.route.name === "stack") {
    try {
      const stackId = encodeURIComponent(state.route.stackId);
      const [detailResponse, logsResponse, auditDetailResponse] = await Promise.all([
        request(apiPath(`stacks/${stackId}`)),
        request(apiPath(`stacks/${stackId}/logs?tail=120`)),
        request(apiPath(`audit?limit=12&stack_id=${stackId}`)),
      ]);
      state.detail = detailResponse;
      state.logs = logsResponse.result?.output || "";
      state.detailAudit = auditDetailResponse.items || [];
    } catch (error) {
      state.detailError = error.message;
    }
  }

  if (state.route.name === "aliases" && state.meta?.mdns_enabled) {
    const aliasResponse = await request(apiPath("mdns/aliases"));
    state.aliases = aliasResponse.items || [];
  }
}

async function navigateTo(url, { replace = false } = {}) {
  const target = new URL(url, window.location.href);
  const nextLocation = `${target.pathname}${target.search}${target.hash}`;
  const currentLocation = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextLocation === currentLocation) {
    return;
  }
  if (replace) {
    window.history.replaceState({}, "", nextLocation);
  } else {
    window.history.pushState({}, "", nextLocation);
  }
  renderShellOnly();
  await loadCurrentPage();
  render();
  window.scrollTo({ top: 0, behavior: "auto" });
}

document.getElementById("refresh-button").addEventListener("click", async () => {
  try {
    await loadCurrentPage();
    render();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById("sidebar-toggle").addEventListener("click", () => {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  window.localStorage.setItem(SIDEBAR_STORAGE_KEY, state.sidebarCollapsed ? "1" : "0");
  renderShellState();
});

document.addEventListener("click", async (event) => {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  const anchor = event.target.closest("a[href]");
  if (!anchor) {
    return;
  }
  if (anchor.target && anchor.target.toLowerCase() !== "_self") {
    return;
  }
  if (anchor.hasAttribute("download")) {
    return;
  }
  const target = new URL(anchor.href, window.location.href);
  if (!isInternalAppUrl(target)) {
    return;
  }
  event.preventDefault();
  try {
    await navigateTo(target.toString());
  } catch (error) {
    handleError(error);
  }
});

window.addEventListener("popstate", async () => {
  try {
    renderShellOnly();
    await loadCurrentPage();
    render();
  } catch (error) {
    handleError(error);
  }
});

loadCurrentPage()
  .then(() => {
    render();
  })
  .catch((error) => {
    document.body.innerHTML = `<pre class="code-block">${escapeHtml(error.message)}</pre>`;
  });
