const SESSION_KEY = 'pharmacy-search-session-id';

export function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
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
