import { ApiError, api } from "./api.js";

const PROFILES = {
  xray: [
    { value: "xray-reality", label: "Xray Reality" },
    { value: "xray-grpc", label: "Xray gRPC" },
    { value: "xray-xhttp", label: "Xray xHTTP" },
  ],
  hysteria2: [{ value: "hysteria2", label: "Hysteria2" }],
};

const REGENERATE_POLICY_FIELDS = {
  "xray-reality": [
    { key: "rotate_port", label: "Порт", default: true },
    { key: "rotate_client_id", label: "UUID клиента", default: true },
    { key: "rotate_reality_keys", label: "Reality privateKey / pbk", default: true },
    { key: "rotate_short_ids", label: "shortIds", default: true },
    { key: "rotate_dest", label: "dest / serverNames", default: true },
  ],
  "xray-xhttp": [
    { key: "rotate_port", label: "Порт", default: true },
    { key: "rotate_client_id", label: "UUID клиента", default: true },
    { key: "rotate_path", label: "xHTTP path", default: true },
    { key: "rotate_tls", label: "TLS cert (self-signed)", default: true },
  ],
  "xray-grpc": [
    { key: "rotate_port", label: "Порт", default: true },
    { key: "rotate_client_id", label: "UUID клиента", default: true },
    { key: "rotate_service_name", label: "gRPC serviceName", default: false },
    { key: "rotate_tls", label: "TLS cert (self-signed)", default: true },
  ],
  hysteria2: [
    { key: "rotate_port", label: "Порт", default: true },
    { key: "rotate_tls", label: "TLS cert (self-signed)", default: true },
    { key: "rotate_auth", label: "Hysteria auth", default: false },
    { key: "rotate_obfs", label: "Hysteria obfs", default: false },
  ],
};

function policyFieldsForProfile(profile) {
  return REGENERATE_POLICY_FIELDS[profile] || [];
}

function isLongPublicKey(value) {
  const text = String(value || "");
  return text.includes("BEGIN ") || text.length > 96;
}

function publicKeyPreview(value) {
  const text = String(value || "").trim();
  if (!text) return "—";
  if (!isLongPublicKey(text)) return text;
  const first = text.split(/\r?\n/).find((line) => line.trim()) || text;
  const compact = first.length > 64 ? `${first.slice(0, 64)}…` : first;
  return compact;
}

function renderPublicKeyField(version) {
  const value = version?.public_key || "";
  if (!value) {
    return `<dl class="detail-item"><dt>Public key</dt><dd>—</dd></dl>`;
  }
  const downloadName = value.includes("BEGIN CERTIFICATE")
    ? `config-${version.id || "cert"}.pem`
    : `config-${version.id || "key"}.txt`;
  if (!isLongPublicKey(value)) {
    return `
      <dl class="detail-item detail-item-wide">
        <dt>Public key</dt>
        <dd>
          <code class="key-inline">${escapeHtml(value)}</code>
          <div class="btn-row" style="margin-top:0.5rem">
            <button type="button" class="secondary download-public-key-btn" data-filename="${escapeHtml(downloadName)}">Скачать</button>
          </div>
          <textarea class="public-key-source hidden" readonly>${escapeHtml(value)}</textarea>
        </dd>
      </dl>
    `;
  }
  return `
    <dl class="detail-item detail-item-wide">
      <dt>Public key / сертификат</dt>
      <dd>
        <details class="pem-fold">
          <summary>${escapeHtml(publicKeyPreview(value))} · развернуть</summary>
          <pre class="pem-body">${escapeHtml(value)}</pre>
        </details>
        <div class="btn-row" style="margin-top:0.5rem">
          <button type="button" class="secondary download-public-key-btn" data-filename="${escapeHtml(downloadName)}">Скачать</button>
        </div>
        <textarea class="public-key-source hidden" readonly>${escapeHtml(value)}</textarea>
      </dd>
    </dl>
  `;
}

function renderVersionCardHtml(version) {
  return `
    <h2 class="card-title">Текущая версия</h2>
    <div class="detail-grid">
      <dl class="detail-item"><dt>Порт</dt><dd>${version.port}</dd></dl>
      ${renderPublicKeyField(version)}
      <dl class="detail-item"><dt>Cert fingerprint</dt><dd class="break-all">${escapeHtml(version.cert_fingerprint || "—")}</dd></dl>
      <dl class="detail-item"><dt>Создана</dt><dd>${escapeHtml(formatDate(version.created_at))}</dd></dl>
    </div>
  `;
}

function bindPublicKeyDownload(root = document) {
  root.querySelectorAll(".download-public-key-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const source = button.closest("dd")?.querySelector(".public-key-source");
      const text = source?.value || source?.textContent || "";
      if (!text) {
        showToast("Нечего скачивать", "error");
        return;
      }
      downloadTextFile(button.dataset.filename || "public-key.txt", text);
    });
  });
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "application/x-pem-file;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderPolicyChecksHtml(profile, values = {}) {
  const fields = policyFieldsForProfile(profile);
  if (!fields.length) return "";
  return `
    <div class="policy-checks">
      ${fields
        .map((item) => {
          const checked = values[item.key] ?? item.default;
          return `
            <label class="policy-check">
              <input type="checkbox" data-policy-key="${escapeHtml(item.key)}" ${checked ? "checked" : ""}>
              <span>${escapeHtml(item.label)}</span>
            </label>
          `;
        })
        .join("")}
    </div>
  `;
}

function readPolicyChecks(container) {
  const regenerate_policy = {};
  container?.querySelectorAll("input[data-policy-key]").forEach((input) => {
    regenerate_policy[input.dataset.policyKey] = input.checked;
  });
  return regenerate_policy;
}

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

async function copyTextToClipboard(text) {
  const value = String(text ?? "");
  if (!value) {
    throw new Error("Нечего копировать");
  }
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error("Не удалось скопировать в буфер обмена");
  }
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
  let label;
  if (status.runtime_online) {
    label = "VPN доступен";
  } else if (status.runtime_systemd_active) {
    label = "Сервис запущен, проверка не прошла";
  } else {
    label = "VPN недоступен";
  }
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
      <fieldset class="field" id="create-policy-fieldset">
        <legend>При regenerate ротировать</legend>
        <div id="create-policy-fields"></div>
      </fieldset>
      <div id="create-error" class="error-box hidden"></div>
      <div class="btn-row">
        <button type="submit">Создать</button>
        <button type="button" class="secondary" id="create-cancel">Отмена</button>
      </div>
    </form>
  `;

  const protocolEl = dialog.querySelector("#create-protocol");
  const profileEl = dialog.querySelector("#create-profile");
  const policyFieldsEl = dialog.querySelector("#create-policy-fields");

  function syncPolicyFields() {
    policyFieldsEl.innerHTML = renderPolicyChecksHtml(profileEl.value);
  }

  function syncProfiles() {
    const protocol = protocolEl.value;
    profileEl.innerHTML = PROFILES[protocol]
      .map((item) => `<option value="${item.value}">${escapeHtml(item.label)}</option>`)
      .join("");
    syncPolicyFields();
  }

  protocolEl.addEventListener("change", syncProfiles);
  profileEl.addEventListener("change", syncPolicyFields);
  syncProfiles();

  dialog.querySelector("#create-cancel").addEventListener("click", () => dialog.close());
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorEl = dialog.querySelector("#create-error");
    errorEl.classList.add("hidden");
    const submitBtn = dialog.querySelector("button[type=submit]");
    submitBtn.disabled = true;

    const regenerate_policy = readPolicyChecks(policyFieldsEl);

    try {
      const result = await api.createConfig({
        name: dialog.querySelector("#create-name").value.trim(),
        protocol: protocolEl.value,
        profile: profileEl.value,
        regenerate_policy,
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
    const bodyEl = document.getElementById("detail-body");
    const alreadyRendered =
      bodyEl?.dataset.configId === configId && bodyEl.querySelector("#detail-status-slot");
    if (alreadyRendered) {
      patchConfigDetailStatus(config, status);
    } else {
      renderConfigDetailContent(config, status);
    }
    if (config.status !== "pending" && config.status !== "processing" && config.status !== "active") {
      stopPolling();
    }
  } catch (error) {
    stopPolling();
    showToast(errorMessage(error), "error");
  }
}

function patchConfigDetailStatus(config, status) {
  const statusSlot = document.getElementById("detail-status-slot");
  if (statusSlot) {
    statusSlot.innerHTML = configStatusDisplay(config.status, status.runtime_online ?? null);
  }
  const runtimeSlot = document.getElementById("detail-runtime-slot");
  if (runtimeSlot) {
    runtimeSlot.innerHTML = runtimeStatusLine(status) || "";
  }
  const errorSlot = document.getElementById("detail-error-slot");
  if (errorSlot) {
    const message = config.error_message || status.error_message;
    errorSlot.innerHTML = message
      ? `<div class="error-box">${escapeHtml(message)}</div>`
      : "";
  }
  const versionEl = document.getElementById("detail-version-value");
  if (versionEl) {
    versionEl.textContent = config.current_version ?? "—";
  }
  const taskEl = document.getElementById("detail-task-value");
  if (taskEl) {
    taskEl.textContent = status.task_id ?? config.last_task_id ?? "—";
  }
  const updatedEl = document.getElementById("detail-updated-value");
  if (updatedEl) {
    updatedEl.textContent = formatDate(config.updated_at);
  }
  // After regenerate finishes, refresh version card once without wiping share-result.
  const versionCard = document.getElementById("detail-version-card");
  const version = config.current_version_detail;
  if (versionCard && version) {
    versionCard.innerHTML = renderVersionCardHtml(version);
    bindPublicKeyDownload(versionCard);
  }
  const regenerateBtn = document.getElementById("regenerate-btn");
  if (regenerateBtn) {
    const canRegenerate = config.status === "active" || config.status === "failed";
    regenerateBtn.disabled = !canRegenerate;
  }
  const canShare = config.status === "active";
  document.getElementById("share-secure-btn") && (document.getElementById("share-secure-btn").disabled = !canShare);
  document.getElementById("share-insecure-btn") && (document.getElementById("share-insecure-btn").disabled = !canShare);
}

function renderConfigDetailContent(config, status) {
  const bodyEl = document.getElementById("detail-body");
  const version = config.current_version_detail;
  const canShare = config.status === "active";
  const canRegenerate = config.status === "active" || config.status === "failed";
  const profile = config.profile || (config.protocol === "hysteria2" ? "hysteria2" : "xray-reality");
  const policyValues = config.regenerate_policy || {};
  const policyHtml = renderPolicyChecksHtml(profile, policyValues);

  bodyEl.dataset.configId = config.id;
  bodyEl.innerHTML = `
    <section class="card">
      <div class="toolbar">
        <h1 class="card-title" style="margin:0">${escapeHtml(config.name)}</h1>
        <div id="detail-status-slot">${configStatusDisplay(config.status, status.runtime_online ?? null)}</div>
      </div>
      <div id="detail-runtime-slot">${runtimeStatusLine(status) || ""}</div>
      <div class="detail-grid">
        <dl class="detail-item"><dt>ID</dt><dd>${escapeHtml(config.id)}</dd></dl>
        <dl class="detail-item"><dt>Протокол</dt><dd>${escapeHtml(config.protocol)}</dd></dl>
        <dl class="detail-item"><dt>Профиль</dt><dd>${escapeHtml(profile)}</dd></dl>
        <dl class="detail-item"><dt>Версия</dt><dd id="detail-version-value">${config.current_version ?? "—"}</dd></dl>
        <dl class="detail-item"><dt>Создан</dt><dd>${escapeHtml(formatDate(config.created_at))}</dd></dl>
        <dl class="detail-item"><dt>Обновлён</dt><dd id="detail-updated-value">${escapeHtml(formatDate(config.updated_at))}</dd></dl>
        <dl class="detail-item"><dt>Task ID</dt><dd id="detail-task-value">${escapeHtml(status.task_id ?? config.last_task_id ?? "—")}</dd></dl>
        ${
          status.task_status
            ? `<dl class="detail-item"><dt>Статус задачи</dt><dd>${escapeHtml(status.task_status)}</dd></dl>`
            : ""
        }
      </div>
      <div id="detail-error-slot">
        ${
          config.error_message || status.error_message
            ? `<div class="error-box">${escapeHtml(config.error_message || status.error_message)}</div>`
            : ""
        }
      </div>
    </section>

    ${
      version
        ? `
      <section class="card" id="detail-version-card">
        ${renderVersionCardHtml(version)}
      </section>
    `
        : `<section class="card" id="detail-version-card" hidden></section>`
    }

    ${
      version
        ? `
      <section class="card" id="config-editor-card">
        <div class="toolbar">
          <h2 class="card-title" style="margin:0">Конфигурация</h2>
          <button type="button" class="secondary" id="config-editor-toggle">Редактировать</button>
        </div>
        <div id="config-editor-panel" class="hidden">
          <div class="toolbar" style="margin-top:0.75rem">
            <span id="config-editor-format" class="muted"></span>
            <div class="btn-row">
              <button type="button" class="secondary" id="config-editor-load">Перезагрузить</button>
              <button type="button" id="config-editor-save" disabled>Сохранить</button>
              <button type="button" class="secondary" id="config-editor-close">Свернуть</button>
            </div>
          </div>
          <div id="config-editor-host" class="config-editor-host" style="margin-top:0.75rem"></div>
          <div id="config-editor-status" class="muted" style="margin-top:0.5rem"></div>
        </div>
      </section>
    `
        : ""
    }

    ${
      policyHtml
        ? `
      <section class="card">
        <h2 class="card-title">При regenerate ротировать</h2>
        <fieldset class="field" id="detail-policy-fieldset" style="margin-bottom:0.75rem">
          <legend>Параметры</legend>
          <div id="detail-policy-fields">${policyHtml}</div>
        </fieldset>
        <div class="btn-row">
          <button type="button" class="secondary" id="save-policy-btn">Сохранить политику</button>
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
  document.getElementById("save-policy-btn")?.addEventListener("click", () =>
    handleSavePolicy(config.id),
  );
  bindPublicKeyDownload(bodyEl);
  bindConfigEditor(config.id);
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

async function handleSavePolicy(configId) {
  const fieldsEl = document.getElementById("detail-policy-fields");
  const regenerate_policy = readPolicyChecks(fieldsEl);
  const button = document.getElementById("save-policy-btn");
  if (button) button.disabled = true;
  try {
    await api.updateRegeneratePolicy(configId, regenerate_policy);
    showToast("Политика regenerate сохранена", "success");
  } catch (error) {
    showToast(errorMessage(error), "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function bindConfigEditor(configId) {
  const panel = document.getElementById("config-editor-panel");
  const host = document.getElementById("config-editor-host");
  const toggleBtn = document.getElementById("config-editor-toggle");
  const closeBtn = document.getElementById("config-editor-close");
  const loadBtn = document.getElementById("config-editor-load");
  const saveBtn = document.getElementById("config-editor-save");
  const statusEl = document.getElementById("config-editor-status");
  const formatEl = document.getElementById("config-editor-format");
  if (!panel || !host || !toggleBtn || !loadBtn || !saveBtn) return;

  let editor = null;
  let loaded = false;
  let currentFormat = "json";
  let open = false;

  function syncSaveEnabled() {
    const ok = loaded && editor && !editor.hasLintErrors();
    saveBtn.disabled = !ok;
  }

  function collapseEditor() {
    open = false;
    panel.classList.add("hidden");
    toggleBtn.classList.remove("hidden");
    if (editor) {
      editor.destroy();
      editor = null;
      host.innerHTML = "";
    }
    loaded = false;
    saveBtn.disabled = true;
    if (statusEl) statusEl.textContent = "";
    if (formatEl) formatEl.textContent = "";
  }

  async function loadEditor() {
    loadBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Загрузка…";
    try {
      const { createConfigEditor } = await import("./lib/config-editor.bundle.js");
      const result = await api.getConfigData(configId);
      currentFormat = result.format === "yaml" ? "yaml" : "json";
      if (formatEl) {
        formatEl.textContent = currentFormat.toUpperCase();
      }
      if (editor) {
        editor.destroy();
        editor = null;
        host.innerHTML = "";
      }
      editor = createConfigEditor(host, {
        format: currentFormat,
        doc: result.content || "",
        onChange: () => syncSaveEnabled(),
      });
      loaded = true;
      syncSaveEnabled();
      if (statusEl) {
        statusEl.textContent = `Версия ${result.version} · ${result.profile}`;
      }
      editor.focus();
    } catch (error) {
      if (statusEl) statusEl.textContent = "";
      showToast(errorMessage(error), "error");
    } finally {
      loadBtn.disabled = false;
    }
  }

  async function openEditor() {
    open = true;
    panel.classList.remove("hidden");
    toggleBtn.classList.add("hidden");
    await loadEditor();
  }

  toggleBtn.addEventListener("click", () => {
    if (!open) openEditor();
  });
  closeBtn?.addEventListener("click", () => collapseEditor());
  loadBtn.addEventListener("click", () => loadEditor());

  saveBtn.addEventListener("click", async () => {
    if (!loaded || !editor) {
      showToast("Сначала откройте редактор", "error");
      return;
    }
    if (editor.hasLintErrors()) {
      syncSaveEnabled();
      showToast("Исправьте ошибки синтаксиса перед сохранением", "error");
      return;
    }
    if (!confirm("Сохранить конфигурацию и перезаписать live-файлы?")) return;
    saveBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Сохранение…";
    try {
      const result = await api.updateConfigData(configId, {
        content: editor.getValue(),
        format: currentFormat,
      });
      editor.setValue(result.content || "");
      syncSaveEnabled();
      if (statusEl) statusEl.textContent = `Сохранено · версия ${result.version}`;
      showToast("Конфигурация сохранена", "success");
    } catch (error) {
      if (statusEl) statusEl.textContent = "";
      showToast(errorMessage(error), "error");
      syncSaveEnabled();
    }
  });
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
      try {
        await copyTextToClipboard(document.getElementById(targetId)?.textContent ?? "");
        showToast("Ссылка скопирована", "success");
      } catch (error) {
        showToast(errorMessage(error), "error");
      }
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
