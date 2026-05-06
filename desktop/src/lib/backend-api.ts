export interface BackendUser {
  id: string;
  email: string;
  username: string;
  name: string;
  full_name: string | null;
  bio: string | null;
  photo_uri: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

const API_BASE_URL =
  import.meta.env.VITE_BACKEND_API_URL ?? "http://localhost:4000/api/v1";

const ACCESS_TOKEN_KEY = "SNC_ACCESS_TOKEN";
const REFRESH_TOKEN_KEY = "SNC_REFRESH_TOKEN";
const DEVICE_ID_KEY = "SNC_DESKTOP_DEVICE_ID";

const authHeader = () => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const parseError = async (response: Response) => {
  try {
    const body = await response.json();
    return body?.message ?? body?.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
};

export const backendRequest = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const headers = {
    "Content-Type": "application/json",
    ...authHeader(),
    ...(init.headers ?? {}),
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
};

export const storeTokens = (tokens: TokenResponse) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
};

export const clearTokens = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

export const hasStoredToken = () => Boolean(localStorage.getItem(ACCESS_TOKEN_KEY));

export const loginRequest = (email: string, password: string) =>
  backendRequest<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const signupRequest = (name: string, email: string, password: string) =>
  backendRequest<BackendUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username: name.trim().replace(/\s+/g, "_"),
      full_name: name.trim(),
      email,
      password,
    }),
  });

export const meRequest = () => backendRequest<BackendUser>("/auth/me");

export const updateProfileRequest = (data: { name?: string; bio?: string }) =>
  backendRequest<BackendUser>("/auth/profile", {
    method: "PUT",
    body: JSON.stringify({
      full_name: data.name,
      bio: data.bio,
    }),
  });

export const logoutRequest = async () => {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) {
    return;
  }
  await backendRequest<{ message: string }>("/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).catch(() => undefined);
};

const desktopDeviceId = () => {
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }
  const generated = `desktop-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  localStorage.setItem(DEVICE_ID_KEY, generated);
  return generated;
};

export const registerDesktopDevice = async () => {
  await backendRequest<{ message: string }>("/devices/register", {
    method: "POST",
    body: JSON.stringify({
      device_id: desktopDeviceId(),
      platform: "windows-desktop",
      app_version: "desktop-tauri",
    }),
  }).catch(() => undefined);
};
