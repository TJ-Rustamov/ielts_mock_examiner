import { fetchJson } from './backend';

const AUTH_TOKEN_KEY = 'auth_token';
const AUTH_USER_KEY = 'auth_user';

type AuthUser = {
  id: number;
  username: string;
  is_staff?: boolean;
  is_superuser?: boolean;
};

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAuthToken());
}

export function getCurrentUser(): AuthUser | null {
  const raw = localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function isAdminUser(): boolean {
  const user = getCurrentUser();
  return Boolean(user && (user.is_staff || user.is_superuser));
}

function setAuth(token: string, user: AuthUser): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function logoutLocal(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

export async function register(username: string, password: string): Promise<AuthUser> {
  const data = await fetchJson<{ token: string; user: AuthUser }>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setAuth(data.token, data.user);
  return data.user;
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const data = await fetchJson<{ token: string; user: AuthUser }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setAuth(data.token, data.user);
  return data.user;
}

export async function logoutRemote(): Promise<void> {
  try {
    await fetchJson<{ success: boolean }>('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  } catch {
    // Ignore server-side logout errors and clear local auth state.
  }
  logoutLocal();
}
