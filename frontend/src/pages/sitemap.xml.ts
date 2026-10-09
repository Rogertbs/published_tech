import type { APIRoute } from "astro";

export const GET: APIRoute = async ({ url }) => {
  const base = process.env.PUBLIC_SITE_URL || url.origin;
  const api = process.env.API_BASE_URL || import.meta.env.API_BASE_URL || "http://127.0.0.1:8000";
  let home = { artigos: [], destaques_github: [], radar_hf: [] };
  try {
    const resp = await fetch(`${api}/api/publico/home`);
    if (resp.ok) home = await resp.json();
  } catch {
    console.warn("Sitemap: falha ao consultar a API pública.");
  }

  const todas = [...home.artigos, ...home.destaques_github, ...home.radar_hf];
  const caminhos = [
    "/",
    "/secao/artigos",
    "/secao/destaques-github",
    "/secao/radar-hf",
    "/sobre",
    ...todas.flatMap((item) => [
      `/artigo/${item.slug}`,
      ...Array.from({ length: item.itens_count || 0 }, (_, i) => `/artigo/${item.slug}/item/${i + 1}`),
    ]),
  ];
  const corpo = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${caminhos.map((c) => `  <url><loc>${base}${c}</loc></url>`).join("\n")}
</urlset>`;
  return new Response(corpo, { headers: { "content-type": "application/xml; charset=utf-8" } });
};
