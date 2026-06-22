import { ApiError, api } from "./api.js";

const PROFILES = {
  xray: [
    { value: "xray-reality", label: "Xray Reality" },
    { value: "xray-grpc", label: "Xray gRPC" },
    { value: "xray-xhttp", label: "Xray xHTTP" },
  ],
  hysteria2: [{ value: "hysteria2", label: "Hysteria2" }],
};

const STATUS_LABELS = {
  pending: "Ожидание",
  processing: "Обработка",
  active: "Активен",
  failed: "Ошибка",
  offline: "Недоступен",
};

const appEl = document.getElementById("app");
const toastEl = document.getElementById("toast");

let pollTimer = null;
let resourcesPollTimer = null;
let runtimePollTimer = null;
let toastTimer = null;
let runtimeById = {};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU");
}

function showToast(message, type = "info") {
  toastEl.textContent = message;
  toastEl.className = `toast ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.className = "toast hidden";
  }, 4000);
}

function errorMessage(error) {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (Array.isArray(error.detail)) {
      return error.detail.map((item) => item.msg ?? JSON.stringify(item)).join("; ");
    }
  }
  return error?.message ?? "Неизвестная ошибка";
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (resourcesPollTimer) {
    clearInterval(resourcesPollTimer);
    resourcesPollTimer = null;
  }
  if (runtimePollTimer) {
    clearInterval(runtimePollTimer);
    runtimePollTimer = null;
  }
}

function formatBytes(bytes) {
  if (bytes == null) return "";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  const digits = exponent === 0 ? 0 : value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[exponent]}`;
}

function resourceLevel(percent) {
  if (percent >= 90) return "critical";
  if (percent >= 70) return "warning";
  return "ok";
}

function renderResourceRing(label, percent, detail = "") {
  const level = resourceLevel(percent);
  return `
    <div class="resource-card">
      <div class="resource-ring resource-ring--${level}" style="--percent: ${percent}">
        <svg viewBox="0 0 36 36" aria-hidden="true">
          <circle class="resource-ring-bg" cx="18" cy="18" r="15.9155"></circle>
          <circle class="resource-ring-fill" cx="18" cy="18" r="15.9155" pathLength="100"></circle>
        </svg>
        <span class="resource-ring-value">${Math.round(percent)}%</span>
      </div>
      <div class="resource-meta">
        <div class="resource-label">${escapeHtml(label)}</div>
        ${detail ? `<div class="resource-detail muted">${escapeHtml(detail)}</div>` : ""}
      </div>
    </div>
  `;
}

function renderResourcesPanel(data) {
  const memoryDetail =
    data.memory.used_bytes != null && data.memory.total_bytes != null
      ? `${formatBytes(data.memory.used_bytes)} / ${formatBytes(data.memory.total_bytes)}`
      : "";
  const swapDetail =
    data.swap.total_bytes
      ? data.swap.used_bytes != null && data.swap.total_bytes != null
        ? `${formatBytes(data.swap.used_bytes)} / ${formatBytes(data.swap.total_bytes)}`
        : ""
      : "не используется";
  const diskDetail =
    data.disk.used_bytes != null && data.disk.total_bytes != null
      ? `${formatBytes(data.disk.used_bytes)} / ${formatBytes(data.disk.total_bytes)}`
      : "";

  return `
    <div class="resource-grid">
      ${renderResourceRing("CPU", data.cpu.percent)}
      ${renderResourceRing("RAM", data.memory.percent, memoryDetail)}
      ${renderResourceRing("SWAP", data.swap.percent, swapDetail)}
      ${renderResourceRing("Disk", data.disk.percent, diskDetail)}
    </div>
    <p class="muted resource-footnote">Диск: ${escapeHtml(data.disk_path)}</p>
  `;
}

async function loadSystemResources() {
  const bodyEl = document.getElementById("resources-body");
  if (!bodyEl) return;

  try {
    const data = await api.getSystemResources();
    bodyEl.innerHTML = renderResourcesPanel(data);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      api.clearToken();
      navigate("/login");
      return;
    }
    bodyEl.innerHTML = `<div class="error-box">${escapeHtml(errorMessage(error))}</div>`;
  }
}

function startResourcesPolling() {
  if (resourcesPollTimer) {
    clearInterval(resourcesPollTimer);
  }
  resourcesPollTimer = setInterval(loadSystemResources, 5000);
}

function startRuntimePolling() {
  if (runtimePollTimer) {
    clearInterval(runtimePollTimer);
  }
  runtimePollTimer = setInterval(loadConfigsRuntime, 5000);
}

function navigate(path) {
  stopPolling();
  if (path === "/login") {
    history.pushState(null, "", "#/login");
    renderLogin();
    return;
  }
  if (path === "/configs") {
    history.pushState(null, "", "#/configs");
    renderConfigs();
    return;
  }
  const match = path.match(/^\/configs\/([0-9a-f-]+)$/i);
  if (match) {
    history.pushState(null, "", `#/configs/${match[1]}`);
    renderConfigDetail(match[1]);
    return;
  }
  history.replaceState(null, "", "#/configs");
  renderConfigs();
}

function parseRoute() {
  const hash = location.hash.replace(/^#/, "") || "/configs";
  if (hash === "/login") return "/login";
  if (hash === "/configs" || hash === "/") return "/configs";
  const match = hash.match(/^\/configs\/([0-9a-f-]+)$/i);
  if (match) return `/configs/${match[1]}`;
  return "/configs";
}

function requireAuth() {
  if (!api.token) {
    navigate("/login");
    return false;
  }
  return true;
}

function layoutHeader(title, actionsHtml = "") {
  return `
    <header class="layout-header">
      <div class="brand">VPN Control Panel <span>${escapeHtml(title)}</span></div>
      <div class="btn-row">${actionsHtml}</div>
    </header>
  `;
}

function statusBadge(status, label = null) {
  const text = label ?? STATUS_LABELS[status] ?? status;
  return `<span class="badge badge-${escapeHtml(status)}">${escapeHtml(text)}</span>`;
}

function configStatusDisplay(configStatus, runtimeOnline = null) {
  if (configStatus === "active" && runtimeOnline === false) {
    return statusBadge("offline");
  }
  return statusBadge(configStatus);
}

function runtimeStatusLine(status) {
  if (status?.runtime_online !== true && status?.runtime_online !== false) {
    return "";
  }
  const label = status.runtime_online ? "VPN доступен" : "VPN недоступен";
  const badge = status.runtime_online ? statusBadge("active", label) : statusBadge("offline", label);
  const detail = status.runtime_detail ? `<span class="muted">${escapeHtml(status.runtime_detail)}</span>` : "";
  return `<div class="runtime-status">${badge} ${detail}</div>`;
}

function renderLogin() {
  appEl.innerHTML = `
    <div class="login-wrap card">
      <h1 class="card-title">Вход</h1>
      <p class="muted">Админ-панель VPN Control Panel</p>
      <form id="login-form">
        <div class="field">
          <label for="username">Имя пользователя</label>
          <input id="username" name="username" autocomplete="username" required>
        </div>
        <div class="field">
          <label for="password">Пароль</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required>
        </div>
        <div id="login-error" class="error-box hidden"></div>
        <button type="submit">Войти</button>
      </form>
    </div>
  `;

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const errorEl = document.getElementById("login-error");
    errorEl.classList.add("hidden");
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;

    try {
      const data = new FormData(form);
      const result = await api.login(data.get("username"), data.get("password"));
      api.token = result.access_token;
      navigate("/configs");
    } catch (error) {
      errorEl.textContent = errorMessage(error);
      errorEl.classList.remove("hidden");
    } finally {
      submitBtn.disabled = false;
    }
  });
}

function shareTtlFieldHtml(selectId) {
  return `
    <div class="field">
      <label for="${selectId}">TTL</label>
      <select id="${selectId}">
        <option value="">Постоянная</option>
        <option value="3600">1 час</option>
        <option value="86400">24 часа</option>
        <option value="604800">7 дней</option>
        <option value="custom">Свой (секунды)</option>
      </select>
      <input id="${selectId}-custom" type="number" min="1" placeholder="TTL в секундах" class="hidden" style="margin-top:0.5rem">
    </div>
  `;
}

function bindShareTtlSelect(selectId) {
  const select = document.getElementById(selectId);
  const custom = document.getElementById(`${selectId}-custom`);
  if (!select || !custom) return;
  select.addEventListener("change", () => {
    custom.classList.toggle("hidden", select.value !== "custom");
  });
}

function buildSharePayload(secure, selectId) {
  const payload = { secure, is_permanent: true };
  const select = document.getElementById(selectId);
  const custom = document.getElementById(`${selectId}-custom`);
  let ttl = select?.value ?? "";
  if (ttl === "custom") {
    ttl = custom?.value ?? "";
  }
  if (ttl) {
    payload.is_permanent = false;
    payload.ttl_seconds = Number(ttl);
  }
  return payload;
}

function shareExpirationLabel(result) {
  if (result.is_permanent) {
    return "постоянная";
  }
  if (result.expires_at) {
    return `до ${formatDate(result.expires_at)}`;
  }
  return "временная";
}

function formatShareExpires(item) {
  if (item.is_permanent) {
    return "Постоянная";
  }
  if (item.expires_at) {
    return formatDate(item.expires_at);
  }
  return "—";
}

function renderShareLinksTable(items, { revokeHandlerId = "share-links-body" } = {}) {
  if (!items.length) {
    return `<div class="empty-state">Активных share-ссылок нет.</div>`;
  }
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Область</th>
            <th>Secure</th>
            <th>Кем выпущена</th>
            <th>Создана</th>
            <th>Истекает</th>
            <th>Обращений</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map(
              (item) => `
            <tr>
              <td>${escapeHtml(item.all_configs ? "Все конфиги" : item.config_name || item.config_id || "—")}</td>
              <td>${item.secure ? "secure" : "insecure"}</td>
              <td>${escapeHtml(item.created_by)}</td>
              <td>${escapeHtml(formatDate(item.created_at))}</td>
              <td>${escapeHtml(formatShareExpires(item))}</td>
              <td>${item.access_count}</td>
              <td><button type="button" class="link-btn danger revoke-share-link" data-id="${escapeHtml(item.id)}">Отозвать</button></td>
            </tr>
          `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function loadShareLinksList(containerId, params = {}) {
  const bodyEl = document.getElementById(containerId);
  if (!bodyEl) return;
  bodyEl.innerHTML = `<span class="muted">Загрузка…</span>`;
  try {
    const data = await api.listShareLinks(params);
    bodyEl.innerHTML = renderShareLinksTable(data.items);
    bodyEl.querySelectorAll(".revoke-share-link").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirm("Отозвать share-ссылку?")) return;
        try {
          await api.revokeShareLinkById(button.dataset.id);
          showToast("Share-ссылка отозвана", "success");
          await loadShareLinksList(containerId, params);
        } catch (error) {
          showToast(errorMessage(error), "error");
        }
      });
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      api.clearToken();
      navigate("/login");
      return;
    }
    bodyEl.innerHTML = `<div class="error-box">${escapeHtml(errorMessage(error))}</div>`;
  }
}

async function renderConfigs() {
  if (!requireAuth()) return;

  appEl.innerHTML = `
    ${layoutHeader("Обзор", `
      <button type="button" class="secondary" id="logout-btn">Выйти</button>
      <button type="button" id="create-btn">Создать конфиг</button>
    `)}
    <section class="card">
      <div class="toolbar">
        <h2 class="card-title" style="margin:0">Ресурсы сервера</h2>
        <button type="button" class="secondary" id="resources-refresh">Обновить</button>
      </div>
      <div id="resources-body" class="muted">Загрузка…</div>
    </section>
    <section class="card">
      <div class="toolbar">
        <div class="filters">
          <label class="muted" for="protocol-filter">Протокол</label>
          <select id="protocol-filter">
            <option value="">Все</option>
            <option value="xray">Xray</option>
            <option value="hysteria2">Hysteria2</option>
          </select>
        </div>
        <div class="btn-row">
          <button type="button" class="secondary" id="regenerate-all-btn">Regenerate all</button>
          <span id="configs-count" class="muted"></span>
        </div>
      </div>
      <div id="configs-body" class="muted">Загрузка…</div>
    </section>
    <section class="card">
      <h2 class="card-title">Share-ссылки</h2>
      <p class="muted">Агрегированные ссылки на все активные конфиги. При каждом открытии подставляются текущие версии.</p>
      ${shareTtlFieldHtml("share-all-ttl")}
      <div class="btn-row">
        <button type="button" class="secondary" id="share-all-secure">Все конфиги (secure)</button>
        <button type="button" class="secondary" id="share-all-insecure">Все конфиги (insecure)</button>
      </div>
      <div id="share-all-result"></div>
    </section>
    <section class="card">
      <div class="toolbar">
        <h2 class="card-title" style="margin:0">Активные share-ссылки</h2>
        <button type="button" class="secondary" id="share-links-refresh">Обновить</button>
      </div>
      <p class="muted">Неотозванные ссылки, у которых не истёк срок действия. URL хранится только при создании.</p>
      <div id="share-links-body" class="muted">Загрузка…</div>
    </section>
    <dialog id="create-dialog"></dialog>
  `;

  document.getElementById("logout-btn").addEventListener("click", () => {
    api.clearToken();
    navigate("/login");
  });
  document.getElementById("create-btn").addEventListener("click", openCreateDialog);
  document.getElementById("protocol-filter").addEventListener("change", loadConfigsList);
  document.getElementById("regenerate-all-btn")?.addEventListener("click", handleRegenerateAll);
  bindShareTtlSelect("share-all-ttl");
  document.getElementById("share-all-secure")?.addEventListener("click", () =>
    handleAllShare(true, "share-all-result"),
  );
  document.getElementById("share-all-insecure")?.addEventListener("click", () =>
    handleAllShare(false, "share-all-result"),
  );
  document.getElementById("share-links-refresh")?.addEventListener("click", () =>
    loadShareLinksList("share-links-body"),
  );
  document.getElementById("resources-refresh")?.addEventListener("click", loadSystemResources);

  await Promise.all([loadSystemResources(), loadConfigsList(), loadShareLinksList("share-links-body")]);
  startResourcesPolling();
  startRuntimePolling();
}

async function handleRegenerateAll() {
  if (
    !confirm(
      "Поставить в очередь regenerate для всех активных конфигов? Занятые (pending/processing) будут пропущены.",
    )
  ) {
    return;
  }
  const button = document.getElementById("regenerate-all-btn");
  if (button) button.disabled = true;
  try {
    const result = await api.regenerateAllConfigs();
    const queued = result.queued?.length ?? 0;
    const skipped = result.skipped?.length ?? 0;
    showToast(`Regenerate: в очереди ${queued}, пропущено ${skipped}`, "success");
    await loadConfigsList();
  } catch (error) {
    showToast(errorMessage(error), "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadConfigsRuntime() {
  const protocol = document.getElementById("protocol-filter")?.value;
  try {
    const data = await api.getConfigsRuntime(protocol ? { protocol } : {});
    runtimeById = Object.fromEntries(data.items.map((item) => [item.config_id, item]));
    const bodyEl = document.getElementById("configs-body");
    if (!bodyEl) return;
    bodyEl.querySelectorAll("tr [data-runtime-id]").forEach((cell) => {
      const configId = cell.dataset.runtimeId;
      const configStatus = cell.dataset.configStatus;
      const runtime = runtimeById[configId];
      cell.innerHTML = configStatusDisplay(configStatus, runtime?.online ?? null);
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      api.clearToken();
      navigate("/login");
    }
  }
}
async function loadConfigsList() {
  const bodyEl = document.getElementById("configs-body");
  const countEl = document.getElementById("configs-count");
  const protocol = document.getElementById("protocol-filter").value;

  try {
    const data = await api.listConfigs(protocol ? { protocol } : {});
    countEl.textContent = `Всего: ${data.total}`;

    if (!data.items.length) {
      bodyEl.innerHTML = `<div class="empty-state">Конфигов пока нет. Создайте первый.</div>`;
      return;
    }

    bodyEl.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Имя</th>
              <th>Протокол</th>
              <th>Статус</th>
              <th>Версия</th>
              <th>Обновлён</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${data.items
              .map(
                (item) => `
              <tr>
                <td>${escapeHtml(item.name)}</td>
                <td>${escapeHtml(item.protocol)}</td>
                <td data-runtime-id="${escapeHtml(item.id)}" data-config-status="${escapeHtml(item.status)}">${configStatusDisplay(item.status, runtimeById[item.id]?.online ?? null)}</td>
                <td>${item.current_version ?? "—"}</td>
                <td>${escapeHtml(formatDate(item.updated_at))}</td>
                <td><button type="button" class="link-btn" data-id="${escapeHtml(item.id)}">Открыть</button></td>
              </tr>
            `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;

    bodyEl.querySelectorAll("[data-id]").forEach((button) => {
      button.addEventListener("click", () => navigate(`/configs/${button.dataset.id}`));
    });
    await loadConfigsRuntime();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      api.clearToken();
      navigate("/login");
      return;
    }
    bodyEl.innerHTML = `<div class="error-box">${escapeHtml(errorMessage(error))}</div>`;
  }
}

function openCreateDialog() {
  const dialog = document.getElementById("create-dialog");
  dialog.innerHTML = `
    <form method="dialog" class="card" style="border:none;box-shadow:none;min-width:min(420px,90vw)">
      <h2 class="card-title">Новый конфиг</h2>
      <div class="field">
        <label for="create-name">Имя</label>
        <input id="create-name" required maxlength="128" placeholder="Office VPN">
      </div>
      <div class="field">
        <label for="create-protocol">Протокол</label>
        <select id="create-protocol">
          <option value="xray">Xray</option>
          <option value="hysteria2">Hysteria2</option>
        </select>
      </div>
      <div class="field">
        <label for="create-profile">Профиль</label>
        <select id="create-profile"></select>
      </div>
      <div id="create-error" class="error-box hidden"></div>
      <div class="btn-row">
        <button type="submit">Создать</button>
        <button type="button" class="secondary" id="create-cancel">Отмена</button>
      </div>
    </form>
  `;

  const protocolEl = dialog.querySelector("#create-protocol");
  const profileEl = dialog.querySelector("#create-profile");

  function syncProfiles() {
    const protocol = protocolEl.value;
    profileEl.innerHTML = PROFILES[protocol]
      .map((item) => `<option value="${item.value}">${escapeHtml(item.label)}</option>`)
      .join("");
  }

  protocolEl.addEventListener("change", syncProfiles);
  syncProfiles();

  dialog.querySelector("#create-cancel").addEventListener("click", () => dialog.close());
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorEl = dialog.querySelector("#create-error");
    errorEl.classList.add("hidden");
    const submitBtn = dialog.querySelector("button[type=submit]");
    submitBtn.disabled = true;

    try {
      const result = await api.createConfig({
        name: dialog.querySelector("#create-name").value.trim(),
        protocol: protocolEl.value,
        profile: profileEl.value,
      });
      dialog.close();
      showToast("Конфиг создаётся…", "success");
      navigate(`/configs/${result.config_id}`);
    } catch (error) {
      errorEl.textContent = errorMessage(error);
      errorEl.classList.remove("hidden");
    } finally {
      submitBtn.disabled = false;
    }
  });

  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "open");
  }
}

async function renderConfigDetail(configId) {
  if (!requireAuth()) return;

  appEl.innerHTML = `
    ${layoutHeader("Конфиг", `
      <button type="button" class="secondary" id="back-btn">← К списку</button>
      <button type="button" class="secondary" id="logout-btn">Выйти</button>
    `)}
    <div id="detail-body" class="muted">Загрузка…</div>
  `;

  document.getElementById("back-btn").addEventListener("click", () => navigate("/configs"));
  document.getElementById("logout-btn").addEventListener("click", () => {
    api.clearToken();
    navigate("/login");
  });

  await loadConfigDetail(configId);
}

async function loadConfigDetail(configId) {
  const bodyEl = document.getElementById("detail-body");

  try {
    const [config, status] = await Promise.all([
      api.getConfig(configId),
      api.getConfigStatus(configId),
    ]);
    renderConfigDetailContent(config, status);

    if (config.status === "pending" || config.status === "processing") {
      stopPolling();
      pollTimer = setInterval(() => refreshConfigDetail(configId), 2500);
    } else if (config.status === "active") {
      stopPolling();
      pollTimer = setInterval(() => refreshConfigDetail(configId), 5000);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      api.clearToken();
      navigate("/login");
      return;
    }
    bodyEl.innerHTML = `<div class="error-box">${escapeHtml(errorMessage(error))}</div>`;
  }
}

async function refreshConfigDetail(configId) {
  try {
    const [config, status] = await Promise.all([
      api.getConfig(configId),
      api.getConfigStatus(configId),
    ]);
    renderConfigDetailContent(config, status);
    if (config.status !== "pending" && config.status !== "processing" && config.status !== "active") {
      stopPolling();
    }
  } catch (error) {
    stopPolling();
    showToast(errorMessage(error), "error");
  }
}

function renderConfigDetailContent(config, status) {
  const bodyEl = document.getElementById("detail-body");
  const version = config.current_version_detail;
  const canShare = config.status === "active";
  const canRegenerate = config.status === "active" || config.status === "failed";

  bodyEl.innerHTML = `
    <section class="card">
      <div class="toolbar">
        <h1 class="card-title" style="margin:0">${escapeHtml(config.name)}</h1>
        ${configStatusDisplay(config.status, status.runtime_online ?? null)}
      </div>
      ${runtimeStatusLine(status)}
      <div class="detail-grid">
        <dl class="detail-item"><dt>ID</dt><dd>${escapeHtml(config.id)}</dd></dl>
        <dl class="detail-item"><dt>Протокол</dt><dd>${escapeHtml(config.protocol)}</dd></dl>
        <dl class="detail-item"><dt>Версия</dt><dd>${config.current_version ?? "—"}</dd></dl>
        <dl class="detail-item"><dt>Создан</dt><dd>${escapeHtml(formatDate(config.created_at))}</dd></dl>
        <dl class="detail-item"><dt>Обновлён</dt><dd>${escapeHtml(formatDate(config.updated_at))}</dd></dl>
        <dl class="detail-item"><dt>Task ID</dt><dd>${escapeHtml(status.task_id ?? config.last_task_id ?? "—")}</dd></dl>
        ${
          status.task_status
            ? `<dl class="detail-item"><dt>Статус задачи</dt><dd>${escapeHtml(status.task_status)}</dd></dl>`
            : ""
        }
      </div>
      ${
        config.error_message || status.error_message
          ? `<div class="error-box">${escapeHtml(config.error_message || status.error_message)}</div>`
          : ""
      }
    </section>

    ${
      version
        ? `
      <section class="card">
        <h2 class="card-title">Текущая версия</h2>
        <div class="detail-grid">
          <dl class="detail-item"><dt>Порт</dt><dd>${version.port}</dd></dl>
          <dl class="detail-item"><dt>Public key</dt><dd>${escapeHtml(version.public_key || "—")}</dd></dl>
          <dl class="detail-item"><dt>Cert fingerprint</dt><dd>${escapeHtml(version.cert_fingerprint || "—")}</dd></dl>
          <dl class="detail-item"><dt>Создана</dt><dd>${escapeHtml(formatDate(version.created_at))}</dd></dl>
        </div>
      </section>
    `
        : ""
    }

    <section class="card">
      <h2 class="card-title">Действия</h2>
      ${shareTtlFieldHtml("share-ttl")}
      <div class="btn-row">
        <button type="button" id="regenerate-btn" ${canRegenerate ? "" : "disabled"}>Regenerate</button>
        <button type="button" id="share-secure-btn" ${canShare ? "" : "disabled"}>Share (secure)</button>
        <button type="button" id="share-insecure-btn" ${canShare ? "" : "disabled"}>Share (insecure)</button>
        <button type="button" class="danger" id="delete-btn">Удалить</button>
      </div>
      <div id="share-result"></div>
      <section style="margin-top:1rem">
        <div class="toolbar">
          <h3 class="card-title" style="margin:0;font-size:1rem">Активные share-ссылки</h3>
          <button type="button" class="secondary" id="share-links-refresh">Обновить</button>
        </div>
        <div id="share-links-body" class="muted">Загрузка…</div>
      </section>
      <div class="field" style="margin-top:1rem">
        <label for="revoke-token">Отозвать share по token</label>
        <div class="btn-row">
          <input id="revoke-token" placeholder="token из URL">
          <button type="button" class="secondary" id="revoke-btn">Отозвать</button>
        </div>
      </div>
    </section>
  `;

  document.getElementById("regenerate-btn")?.addEventListener("click", () =>
    handleRegenerate(config.id),
  );
  bindShareTtlSelect("share-ttl");
  document.getElementById("share-secure-btn")?.addEventListener("click", () =>
    handleShare(config.id, true),
  );
  document.getElementById("share-insecure-btn")?.addEventListener("click", () =>
    handleShare(config.id, false),
  );
  document.getElementById("delete-btn")?.addEventListener("click", () => handleDelete(config.id));
  document.getElementById("revoke-btn")?.addEventListener("click", handleRevokeShare);
  document.getElementById("share-links-refresh")?.addEventListener("click", () =>
    loadShareLinksList("share-links-body", { config_id: config.id }),
  );
  loadShareLinksList("share-links-body", { config_id: config.id });
}

async function handleRegenerate(configId) {
  if (!confirm("Перегенерировать ключи и создать новую версию?")) return;
  try {
    await api.regenerateConfig(configId);
    showToast("Regenerate запущен", "success");
    await loadConfigDetail(configId);
  } catch (error) {
    showToast(errorMessage(error), "error");
  }
}

async function handleShare(configId, secure) {
  showShareResult("share-result", () =>
    api.createShareLink(configId, buildSharePayload(secure, "share-ttl")),
  );
}

async function handleAllShare(secure, resultId) {
  showShareResult(resultId, () =>
    api.createAllShareLinks(buildSharePayload(secure, "share-all-ttl")),
  );
}

async function showShareResult(resultId, createLink) {
  const resultEl = document.getElementById(resultId);
  try {
    const result = await createLink();
    const scope = result.all_configs
      ? `Все конфиги · ${result.secure ? "secure" : "insecure"} · ${result.config_count ?? "?"} профилей`
      : `${result.secure ? "secure" : "insecure"}`;
    const meta = `${scope} · ${shareExpirationLabel(result)}`;
    resultEl.innerHTML = `
      <div class="share-result">
        <strong>Share-ссылка создана</strong>
        <div class="muted" style="margin-top:0.35rem">${escapeHtml(meta)}</div>
        <code id="share-url-${resultId}">${escapeHtml(result.url)}</code>
        <div class="btn-row" style="margin-top:0.75rem">
          <button type="button" class="secondary copy-share-btn" data-target="share-url-${resultId}">Копировать</button>
        </div>
      </div>
    `;
    resultEl.querySelector(".copy-share-btn")?.addEventListener("click", async (event) => {
      const targetId = event.currentTarget.dataset.target;
      await navigator.clipboard.writeText(document.getElementById(targetId).textContent);
      showToast("Ссылка скопирована", "success");
    });
    if (document.getElementById("share-links-body")) {
      const routeMatch = location.hash.match(/#\/configs\/([0-9a-f-]+)/i);
      await loadShareLinksList(
        "share-links-body",
        routeMatch ? { config_id: routeMatch[1] } : {},
      );
    }
  } catch (error) {
    resultEl.innerHTML = `<div class="error-box">${escapeHtml(errorMessage(error))}</div>`;
  }
}

async function handleDelete(configId) {
  if (!confirm("Удалить конфиг? Это soft delete.")) return;
  try {
    await api.deleteConfig(configId);
    showToast("Конфиг удалён", "success");
    navigate("/configs");
  } catch (error) {
    showToast(errorMessage(error), "error");
  }
}

async function handleRevokeShare() {
  const token = document.getElementById("revoke-token").value.trim();
  if (!token) {
    showToast("Укажите token", "error");
    return;
  }
  try {
    await api.revokeShareLink(token);
    showToast("Share-ссылка отозвана", "success");
    document.getElementById("revoke-token").value = "";
  } catch (error) {
    showToast(errorMessage(error), "error");
  }
}

function bootstrap() {
  window.addEventListener("hashchange", () => navigate(parseRoute()));
  const route = parseRoute();
  if (route === "/login") {
    renderLogin();
    return;
  }
  if (!api.token) {
    navigate("/login");
    return;
  }
  navigate(route);
}

bootstrap();
