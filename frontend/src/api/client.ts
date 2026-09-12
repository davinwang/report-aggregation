// Axios API client. Dev server proxies /api and /health to the FastAPI backend.
import axios, { AxiosError, type AxiosInstance } from "axios";
import { getToken, useAuthStore } from "@/stores/authStore";
import { msg } from "@/utils/message";

export const http: AxiosInstance = axios.create({
  baseURL: "/",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail?: string }>) => {
    const status = err.response?.status;
    if (status === 401) {
      // Clear stale session so guards redirect to /login.
      if (getToken()) useAuthStore.getState().clear();
    } else if (status && status >= 500) {
      msg.error(err.response?.data?.detail || "服务器错误");
    }
    return Promise.reject(err);
  },
);

// Convenience: unwrap the standard { data, meta } envelope.
export async function getData<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await http.get<{ data: T }>(url, { params });
  return res.data.data;
}

export async function getEnvelope<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<{ data: T; meta: Record<string, unknown> }> {
  const res = await http.get(url, { params });
  return res.data;
}
