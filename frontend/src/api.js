import axios from "axios";

const TOKEN_KEY = "skillwatch_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export const api = axios.create({ baseURL: `${import.meta.env.VITE_API_URL || ""}/api` });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// An expired or invalid token anywhere logs the user out (except on the login call itself).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLogin = error.config?.url?.endsWith("/auth/login");
    if (error.response?.status === 401 && !isLogin) {
      clearToken();
      window.dispatchEvent(new Event("skillwatch:logout"));
    }
    return Promise.reject(error);
  }
);

/** Turn an Axios error into one readable sentence. */
export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  if (typeof detail === "string") return detail;
  if (err?.code === "ERR_NETWORK") return "Cannot reach the server. Is the backend running on port 8000?";
  return err?.message || "Something went wrong";
}
