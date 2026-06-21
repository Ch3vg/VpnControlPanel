const TOKEN_KEY = "vpn_panel_token";

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

export class ApiClient {
  get token() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  set token(value) {
    if (value) {
      sessionStorage.setItem(TOKEN_KEY, value);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  }

  clearToken() {
    this.token = null;
  }

  async request(method, path, body) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    const response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (response.status === 204) {
      return null;
    }

    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }

    if (!response.ok) {
      const detail = payload?.detail ?? payload ?? response.statusText;
      throw new ApiError(response.status, detail);
    }

    return payload;
  }

  login(username, password) {
    return this.request("POST", "/auth/login", { username, password });
  }

  listConfigs(params = {}) {
    const query = new URLSearchParams();
    if (params.protocol) query.set("protocol", params.protocol);
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const suffix = query.toString() ? `?${query}` : "";
    return this.request("GET", `/api/v1/configs${suffix}`);
  }

  getConfig(id) {
    return this.request("GET", `/api/v1/configs/${id}`);
  }

  getConfigStatus(id) {
    return this.request("GET", `/api/v1/configs/${id}/status`);
  }

  createConfig(payload) {
    return this.request("POST", "/api/v1/configs", payload);
  }

  regenerateConfig(id) {
    return this.request("POST", `/api/v1/configs/${id}/regenerate`);
  }

  deleteConfig(id) {
    return this.request("DELETE", `/api/v1/configs/${id}`);
  }

  createShareLink(id, payload = { is_permanent: true, secure: true }) {
    return this.request("POST", `/api/v1/configs/${id}/share`, payload);
  }

  createAllShareLinks(payload = { is_permanent: true, secure: true }) {
    return this.request("POST", "/api/v1/share/all", payload);
  }

  listShareLinks(params = {}) {
    const query = new URLSearchParams();
    if (params.config_id) query.set("config_id", params.config_id);
    const suffix = query.toString() ? `?${query}` : "";
    return this.request("GET", `/api/v1/share/links${suffix}`);
  }

  revokeShareLinkById(id) {
    return this.request("DELETE", `/api/v1/share/links/${id}`);
  }

  revokeShareLink(token) {
    return this.request("DELETE", `/api/v1/share/${encodeURIComponent(token)}`);
  }
}

export const api = new ApiClient();
