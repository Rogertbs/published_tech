const API_BASE = process.env.API_BASE_URL || import.meta.env.API_BASE_URL || "http://127.0.0.1:8000";

async function getJson(path) {
  const resp = await fetch(`${API_BASE}${path}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`API ${path} -> ${resp.status}`);
  return resp.json();
}

export function getHome() {
  return getJson("/api/publico/home");
}

export function getSecao(secao) {
  return getJson(`/api/publico/secao/${secao}`);
}

export function getArtigo(slug) {
  return getJson(`/api/publico/artigo/${slug}`);
}

export function getItem(slug, ordem) {
  return getJson(`/api/publico/item/${slug}/${ordem}`);
}

export function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}
