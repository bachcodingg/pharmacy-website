export async function search(query, { literal = false } = {}) {
  const params = new URLSearchParams({ q: query });
  if (literal) params.set('literal', 'true');
  const response = await fetch(`/api/search?${params.toString()}`);
  return response.json();
}

export async function suggest(query) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(query)}`);
  return response.json();
}
