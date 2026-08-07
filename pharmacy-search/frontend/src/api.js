const SESSION_KEY = 'pharmacy-search-session-id';
const TOKEN_KEY = 'pharmacy-search-token';

export function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

export async function search(query, { literal = false } = {}) {
  const params = new URLSearchParams({ q: query, session_id: getSessionId() });
  if (literal) params.set('literal', 'true');
  const response = await fetch(`/api/search?${params.toString()}`);
  return response.json();
}

export async function suggest(query) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(query)}`);
  return response.json();
}

export function logClick(query, product) {
  const params = new URLSearchParams({ session_id: getSessionId(), query, product });
  navigator.sendBeacon
    ? navigator.sendBeacon(`/api/click?${params.toString()}`)
    : fetch(`/api/click?${params.toString()}`, { method: 'POST' });
}

export async function register(email, password, name) {
  const data = await apiFetch('/api/auth/register', { method: 'POST', body: { email, password, name } });
  setToken(data.token);
  return data.user;
}

export async function login(email, password) {
  const data = await apiFetch('/api/auth/login', { method: 'POST', body: { email, password } });
  setToken(data.token);
  return data.user;
}

export async function logout() {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST', auth: true });
  } finally {
    clearToken();
  }
}

export function getMe() {
  return apiFetch('/api/auth/me', { auth: true });
}

export function updateProfile(fields) {
  return apiFetch('/api/auth/me', { method: 'PUT', body: fields, auth: true });
}

export function changePassword(oldPassword, newPassword) {
  return apiFetch('/api/auth/change-password', {
    method: 'POST',
    body: { old_password: oldPassword, new_password: newPassword },
    auth: true,
  });
}

export function forgotPassword(email) {
  return apiFetch('/api/auth/forgot-password', { method: 'POST', body: { email } });
}

export function resetPassword(token, newPassword) {
  return apiFetch('/api/auth/reset-password', { method: 'POST', body: { token, new_password: newPassword } });
}

export function listAddresses() {
  return apiFetch('/api/auth/addresses', { auth: true });
}

export function createAddress(address) {
  return apiFetch('/api/auth/addresses', { method: 'POST', body: address, auth: true });
}

export function deleteAddress(id) {
  return apiFetch(`/api/auth/addresses/${id}`, { method: 'DELETE', auth: true });
}

export function listOrders() {
  return apiFetch('/api/auth/orders', { auth: true });
}

export function listProducts({ q = '', category = '', page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q) params.set('q', q);
  if (category) params.set('category', category);
  return apiFetch(`/api/products?${params.toString()}`);
}

export function getProduct(id) {
  return apiFetch(`/api/products/${id}`);
}

export function listReviews(productId) {
  return apiFetch(`/api/products/${productId}/reviews`);
}

export function createReview(productId, rating, comment) {
  return apiFetch(`/api/products/${productId}/reviews`, {
    method: 'POST',
    body: { rating, comment },
    auth: true,
  });
}
