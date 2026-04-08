const state = {
  meta: null,
  stacks: [],
  selectedStackId: null,
  detail: null,
  logs: "",
  audit: [],
  aliases: [],
  registryStacks: [],
  gitCredential: null,
};

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

function apiPath(path) {
  return `api/${path}`;
}

function handleError(error) {
  window.alert(error.message);
}

function renderAccessCards() {
  const root = document.getElementById("access-cards");
  if (!state.meta) return;
  const cards = [
    ["Primary", state.meta.base_url],
    state.meta.alias_url ? ["Alias", state.meta.alias_url] : null,
    state.meta.fallback_url ? ["Fallback", state.meta.fallback_url] : null,
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

function renderStacks() {
  const root = document.getElementById("stack-list");
  root.innerHTML = state.stacks.length
    ? state.stacks
        .map((stack) => {
          const selected = stack.id === state.selectedStackId ? "selected" : "";
          const git = stack.git?.available
            ? `${stack.git.branch || "-"} / ${stack.git.commit || "-"}${stack.git.dirty ? " *" : ""}`
            : "git unavailable";
          const lastAction = stack.last_action
            ? `${stack.last_action.action} · ${stack.last_action.success ? "success" : "failed"}`
            : "no deploy yet";
          return `
            <article class="stack-item ${selected}" data-stack-id="${escapeHtml(stack.id)}">
              <header>
                <strong class="text-base">${escapeHtml(stack.name)}</strong>
                <span class="${statusClass(stack.status)}">${escapeHtml(stack.status)}</span>
              </header>
              <p class="stack-meta">${escapeHtml(stack.compose_file)}</p>
              <p class="stack-meta">${escapeHtml(`${stack.container_count} containers · ${git}`)}</p>
              <p class="stack-meta">${escapeHtml(lastAction)}</p>
            </article>
          `;
        })
        .join("")
    : '<p class="muted">stack はまだありません。</p>';

  root.querySelectorAll("[data-stack-id]").forEach((element) => {
    element.addEventListener("click", async () => {
      state.selectedStackId = element.dataset.stackId;
      await loadSelectedStack();
      render();
    });
  });
}

function renderDetail() {
  const detailRoot = document.getElementById("stack-detail");
  const actionsRoot = document.getElementById("stack-actions");
  const containerRoot = document.getElementById("container-list");
  const detailTitle = document.getElementById("detail-title");
  const detailStatus = document.getElementById("detail-status");
  const actionOutput = document.getElementById("action-output");
  const logOutput = document.getElementById("log-output");

  if (!state.detail) {
    detailTitle.textContent = "Stack Detail";
    detailStatus.className = "badge badge-ghost";
    detailStatus.textContent = "idle";
    detailRoot.innerHTML = '<p class="muted">Stack を選択してください。</p>';
    actionsRoot.innerHTML = "";
    containerRoot.innerHTML = "";
    actionOutput.textContent = "まだ実行履歴はありません。";
    logOutput.textContent = "Stack を選択すると logs を表示します。";
    return;
  }

  detailTitle.textContent = state.detail.name;
  detailStatus.className = statusClass(state.detail.status);
  detailStatus.textContent = state.detail.status;

  detailRoot.innerHTML = `
    <div class="detail-meta">
      <span>CWD: <code>${escapeHtml(state.detail.cwd)}</code></span>
      <span>Repo: <code>${escapeHtml(state.detail.repo_url || "-")}</code></span>
      <span>Compose: <code>${escapeHtml(state.detail.compose_file)}</code></span>
      <span>Git: ${
        state.detail.git?.available
          ? escapeHtml(
              `${state.detail.git.branch || "-"} / ${state.detail.git.commit || "-"}${state.detail.git.dirty ? " *" : ""}`,
            )
          : "unavailable"
      }</span>
      <span>Registry Tags: ${escapeHtml((state.detail.tags || []).join(", ") || "-")}</span>
      <span>Last Action: ${
        state.detail.last_action
          ? escapeHtml(`${state.detail.last_action.action} (${state.detail.last_action.success ? "success" : "failed"})`)
          : "none"
      }</span>
    </div>
  `;

  const actions = [
    ["clone", "Clone", false],
    ["validate", "Validate", false],
    ["pull", "Pull", false],
    ["up", "Up -d", false],
    ["restart", "Restart", false],
    ["down", "Down", true],
    ["deploy", "Deploy", false],
  ];
  actionsRoot.innerHTML = actions
    .map(
      ([action, label, danger]) =>
        `<button class="btn btn-sm ${danger ? "btn-error" : "btn-primary"}" type="button" data-action="${action}" data-danger="${danger ? "true" : "false"}">${escapeHtml(label)}</button>`,
    )
    .join("");

  actionsRoot.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const action = button.dataset.action;
        if (button.dataset.danger === "true" && !window.confirm(`${state.detail.name} に ${action} を実行しますか？`)) {
          return;
        }
        const record = await request(apiPath(`stacks/${state.detail.id}/actions/${action}`), { method: "POST" });
        actionOutput.textContent = JSON.stringify(record, null, 2);
        await loadAll();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  });

  containerRoot.innerHTML = (state.detail.containers || []).length
    ? state.detail.containers
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
        .join("")
    : `<p class="muted">${escapeHtml(state.detail.compose_error || "container はありません。")}</p>`;

  if (state.detail.last_action?.steps?.length) {
    const lastStep = state.detail.last_action.steps[state.detail.last_action.steps.length - 1];
    if (lastStep.result?.output) {
      actionOutput.textContent = lastStep.result.output;
    }
  }

  logOutput.textContent = state.logs || "log がありません。";
}

function renderAudit() {
  const root = document.getElementById("history-list");
  root.innerHTML = state.audit.length
    ? state.audit
        .map(
          (item) => `
            <article class="history-item">
              <header>
                <strong class="text-sm">${escapeHtml(item.stack_name)}</strong>
                <span class="${statusClass(item.success ? "success" : "failed")}">${escapeHtml(item.action)}</span>
              </header>
              <p class="muted">${escapeHtml(new Date(item.started_at).toLocaleString())}</p>
              <p class="muted">${escapeHtml(`${item.success ? "success" : "failed"} · ${item.steps?.length || 0} steps`)}</p>
            </article>
          `,
        )
        .join("")
    : '<p class="muted">まだ実行履歴はありません。</p>';
}

function renderAliases() {
  const root = document.getElementById("alias-list");
  if (!state.meta?.mdns_enabled) {
    root.innerHTML = '<p class="muted">mDNS feature は無効です。</p>';
    return;
  }
  root.innerHTML = state.aliases.length
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
    : '<p class="muted">まだ alias はありません。</p>';

  root.querySelectorAll("[data-delete-alias]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const alias = button.dataset.deleteAlias;
        if (!window.confirm(`${alias} を削除しますか？`)) {
          return;
        }
        await request(apiPath(`mdns/aliases/${encodeURIComponent(alias)}`), { method: "DELETE" });
        await loadAliases();
        renderAliases();
      } catch (error) {
        handleError(error);
      }
    });
  });
}

function resetStackForm() {
  document.getElementById("stack-form").reset();
  document.getElementById("stack-id-input").readOnly = false;
}

function fillStackForm(stackId) {
  const stack = state.registryStacks.find((item) => item.id === stackId);
  if (!stack) return;
  document.getElementById("stack-id-input").value = stack.id;
  document.getElementById("stack-id-input").readOnly = true;
  document.getElementById("stack-name-input").value = stack.name || "";
  document.getElementById("stack-cwd-input").value = stack.cwd || "";
  document.getElementById("stack-repo-url-input").value = stack.repo_url || "";
  document.getElementById("stack-compose-input").value = stack.compose_file || "compose.yaml";
  document.getElementById("stack-branch-input").value = stack.branch || "";
  document.getElementById("stack-tags-input").value = (stack.tags || []).join(", ");
  document.getElementById("stack-direct-url-input").value = stack.direct_url || "";
  document.getElementById("stack-traefik-url-input").value = stack.traefik_url || "";
  document.getElementById("stack-notes-input").value = stack.notes || "";
}

function renderRegistry() {
  const root = document.getElementById("registry-list");
  root.innerHTML = state.registryStacks.length
    ? state.registryStacks
        .map(
          (stack) => `
            <article class="alias-item">
              <header>
                <strong class="text-sm">${escapeHtml(stack.name)}</strong>
                <span class="badge badge-neutral badge-outline">${escapeHtml(stack.id)}</span>
              </header>
              <p class="muted">${escapeHtml(`${stack.cwd} · ${stack.compose_file}`)}</p>
              <p class="muted">${escapeHtml(stack.repo_url || "-")}</p>
              <p class="muted">${escapeHtml((stack.tags || []).join(", ") || "-")}</p>
              <div class="inline-actions">
                <button class="btn btn-ghost btn-xs" type="button" data-edit-stack="${escapeHtml(stack.id)}">Edit</button>
                <button class="btn btn-ghost btn-xs" type="button" data-delete-stack="${escapeHtml(stack.id)}">Delete</button>
              </div>
            </article>
          `,
        )
        .join("")
    : '<p class="muted">まだ stack registry は空です。</p>';

  root.querySelectorAll("[data-edit-stack]").forEach((button) => {
    button.addEventListener("click", () => {
      fillStackForm(button.dataset.editStack);
    });
  });

  root.querySelectorAll("[data-delete-stack]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const stackId = button.dataset.deleteStack;
        if (!window.confirm(`${stackId} を registry から削除しますか？`)) {
          return;
        }
        await request(apiPath(`settings/stacks/${encodeURIComponent(stackId)}`), { method: "DELETE" });
        if (state.selectedStackId === stackId) {
          state.selectedStackId = null;
        }
        resetStackForm();
        await loadAll();
        render();
      } catch (error) {
        handleError(error);
      }
    });
  });
}

function resetCredentialForm() {
  document.getElementById("credential-form").reset();
  document.getElementById("credential-secret-input").value = "";
}

function fillCredentialForm() {
  document.getElementById("credential-username-input").value = state.gitCredential?.username || "";
  document.getElementById("credential-secret-input").value = "";
}

function renderCredentialStatus() {
  const root = document.getElementById("credential-status");
  if (!state.gitCredential || !state.gitCredential.has_secret) {
    root.innerHTML = '<p class="muted">まだ Git credential はありません。</p>';
    return;
  }
  root.innerHTML = `
    <article class="alias-item">
      <header>
        <strong class="text-sm">System Credential</strong>
        <span class="badge badge-neutral badge-outline">${escapeHtml(state.gitCredential.username)}</span>
      </header>
      <p class="muted">secret saved</p>
      <p class="muted">${escapeHtml(state.gitCredential.updated_at || "")}</p>
    </article>
  `;
}

function render() {
  renderAccessCards();
  renderStacks();
  renderDetail();
  renderAudit();
  renderAliases();
  renderRegistry();
  renderCredentialStatus();
}

async function loadAliases() {
  if (!state.meta?.mdns_enabled) {
    state.aliases = [];
    return;
  }
  const response = await request(apiPath("mdns/aliases"));
  state.aliases = response.items || [];
}

async function loadSettings() {
  const registryResponse = await request(apiPath("settings/stacks"));
  const credentialResponse = await request(apiPath("settings/git-credential"));
  state.registryStacks = registryResponse.items || [];
  state.gitCredential = credentialResponse?.has_secret ? credentialResponse : null;
}

async function loadSelectedStack() {
  if (!state.selectedStackId) {
    state.detail = null;
    state.logs = "";
    return;
  }
  state.detail = await request(apiPath(`stacks/${state.selectedStackId}`));
  const logs = await request(apiPath(`stacks/${state.selectedStackId}/logs?tail=120`));
  state.logs = logs.result?.output || "";
}

async function loadAll() {
  state.meta = await request(apiPath("meta"));
  await loadSettings();
  const stacksResponse = await request(apiPath("stacks"));
  const auditResponse = await request(apiPath("audit?limit=12"));
  state.stacks = stacksResponse.items || [];
  state.audit = auditResponse.items || [];
  if (!state.selectedStackId || !state.stacks.some((stack) => stack.id === state.selectedStackId)) {
    state.selectedStackId = state.stacks[0]?.id || null;
  }
  await loadSelectedStack();
  await loadAliases();
}

document.getElementById("refresh-button").addEventListener("click", async () => {
  try {
    await loadAll();
    render();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById("alias-form").addEventListener("submit", async (event) => {
  try {
    event.preventDefault();
    const alias = document.getElementById("alias-input").value;
    const targetIp = document.getElementById("target-ip-input").value;
    await request(apiPath("mdns/aliases"), {
      method: "POST",
      body: JSON.stringify({
        alias,
        target_ip: targetIp,
      }),
    });
    event.target.reset();
    await loadAliases();
    renderAliases();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById("stack-form").addEventListener("submit", async (event) => {
  try {
    event.preventDefault();
    const payload = {
      id: document.getElementById("stack-id-input").value,
      name: document.getElementById("stack-name-input").value,
      cwd: document.getElementById("stack-cwd-input").value,
      repo_url: document.getElementById("stack-repo-url-input").value,
      compose_file: document.getElementById("stack-compose-input").value,
      branch: document.getElementById("stack-branch-input").value,
      tags: document.getElementById("stack-tags-input").value,
      direct_url: document.getElementById("stack-direct-url-input").value,
      traefik_url: document.getElementById("stack-traefik-url-input").value,
      notes: document.getElementById("stack-notes-input").value,
    };
    await request(apiPath("settings/stacks"), {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resetStackForm();
    await loadAll();
    render();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById("stack-form-reset").addEventListener("click", resetStackForm);
document.getElementById("stack-form-clear").addEventListener("click", resetStackForm);

document.getElementById("credential-form").addEventListener("submit", async (event) => {
  try {
    event.preventDefault();
    await request(apiPath("settings/git-credential"), {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("credential-username-input").value,
        secret: document.getElementById("credential-secret-input").value,
      }),
    });
    await loadSettings();
    renderCredentialStatus();
    fillCredentialForm();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById("credential-form-clear").addEventListener("click", resetCredentialForm);
document.getElementById("credential-delete").addEventListener("click", async () => {
  try {
    if (!window.confirm("システムの Git credential を削除しますか？")) {
      return;
    }
    await request(apiPath("settings/git-credential"), { method: "DELETE" });
    resetCredentialForm();
    await loadSettings();
    renderCredentialStatus();
  } catch (error) {
    handleError(error);
  }
});

loadAll()
  .then(() => {
    render();
    resetStackForm();
    fillCredentialForm();
  })
  .catch((error) => {
    document.body.innerHTML = `<pre class="code-block">${escapeHtml(error.message)}</pre>`;
  });
