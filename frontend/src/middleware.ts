import { defineMiddleware } from "astro:middleware";
import { createClient } from "redis";

let redisClient = null;
let redisTried = false;

async function getRedis() {
  const url = process.env.REDIS_URL || import.meta.env.REDIS_URL;
  if (!url) return null;
  if (!redisClient && !redisTried) {
    redisTried = true;
    try {
      const client = createClient({ url });
      client.on("error", () => {});
      await client.connect();
      redisClient = client;
    } catch {
      redisClient = null;
    }
  }
  return redisClient && redisClient.isOpen ? redisClient : null;
}

function pageKey(pathname) {
  return `pt:page:${pathname}`;
}

// render-once-and-cache: serve the generated HTML from Redis (no TTL) until the
// backend invalidates the page key on publish/edit/retire (ADR-0003).
export const onRequest = defineMiddleware(async (context, next) => {
  const { request } = context;
  if (request.method !== "GET") return next();

  const url = new URL(request.url);
  const redis = await getRedis();
  const key = pageKey(url.pathname);

  if (redis) {
    try {
      const cached = await redis.get(key);
      if (cached) {
        return new Response(cached, {
          status: 200,
          headers: { "content-type": "text/html; charset=utf-8", "x-cache": "HIT" },
        });
      }
    } catch {}
  }

  const response = await next();

  if (redis && response.status === 200) {
    try {
      const html = await response.clone().text();
      await redis.set(key, html); // no TTL
    } catch {}
  }

  return response;
});
