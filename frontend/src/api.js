import axios from "axios";

// ── Cliente con token automático ──────────────────────────────────────────────

const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
});

http.interceptors.request.use(config => {
  const token = localStorage.getItem("ls_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem("ls_token");
      localStorage.removeItem("ls_user");
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = (username, password) =>
  http.post("/auth/login", { username, password }).then(r => r.data);

export const getMe = () =>
  http.get("/auth/me").then(r => r.data);

// ── Licitaciones ──────────────────────────────────────────────────────────────

export const getLicitaciones = (dias = 7) =>
  http.get("/api/licitaciones", { params: { dias } }).then(r => r.data);

export const getPliego = (url) =>
  http.get("/api/pliego", { params: { url } }).then(r => r.data);

export const clearCache = () =>
  http.delete("/api/cache").then(r => r.data);

// ── Admin ─────────────────────────────────────────────────────────────────────

export const getUsers = () =>
  http.get("/admin/users").then(r => r.data);

export const createUser = (data) =>
  http.post("/admin/users", data).then(r => r.data);

export const toggleUser = (username) =>
  http.patch(`/admin/users/${username}/toggle`).then(r => r.data);

export const renewUser = (username) =>
  http.patch(`/admin/users/${username}/renew`).then(r => r.data);

export const deleteUser = (username) =>
  http.delete(`/admin/users/${username}`).then(r => r.data);
