const TOKEN_KEY = "silkreel_token";
const USER_KEY = "silkreel_user";

export function token() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(value) {
  localStorage.setItem(TOKEN_KEY, value);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function storedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function setStoredUser(value) {
  localStorage.setItem(USER_KEY, JSON.stringify(value));
}

export function clearStoredUser() {
  localStorage.removeItem(USER_KEY);
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}
