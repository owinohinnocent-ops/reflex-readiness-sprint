// Relative paths work through the local proxy. A direct file open still renders
// the interface, and points API requests at the normal FastAPI development URL.
const DEFAULT_API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "/api";
const REQUEST_TIMEOUT_MS = 12_000;

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class ReflexApi {
  constructor({ baseUrl = DEFAULT_API_BASE, getToken }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.getToken = getToken;
  }

  async request(path, { method = "GET", body } = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const headers = { Accept: "application/json" };
    const token = this.getToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new ApiError(payload?.detail || "The request could not be completed.", response.status);
      }
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new ApiError("The server took too long to respond. Please try again.");
      if (error instanceof ApiError) throw error;
      throw new ApiError("Unable to reach Reflex. Check that the API is running.");
    } finally {
      clearTimeout(timeout);
    }
  }

  login(phone, password) { return this.request("/auth/login", { method: "POST", body: { phone, password } }); }
  health() { return this.request("/health"); }
  getCurrentUser() { return this.request("/auth/me"); }
  getDeliveries(filters = {}) {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "" && value != null));
    return this.request(`/deliveries${query.size ? `?${query}` : ""}`);
  }
  getDelivery(id) { return this.request(`/deliveries/${id}`); }
  getRiders(filters = {}) {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "" && value != null));
    return this.request(`/riders${query.size ? `?${query}` : ""}`);
  }
  createDelivery(payload) { return this.request("/deliveries", { method: "POST", body: payload }); }
  assignDelivery(id, rider_id, dispatcher_id) {
    return this.request(`/deliveries/${id}/assign`, { method: "POST", body: { rider_id: Number(rider_id), dispatcher_id } });
  }
  updateDeliveryStatus(id, status) {
    return this.request(`/deliveries/${id}/status`, { method: "PATCH", body: { status } });
  }
}
