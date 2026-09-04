/**
 * Development-only static server and same-origin proxy for the existing API.
 * Run `node frontend/server.mjs`, then open http://localhost:5173.
 * It binds to all network interfaces by default, so another device can use
 * http://YOUR-COMPUTER-IP:5173. Configure a remote API with REFLEX_API_ORIGIN.
 */
import { createReadStream, existsSync } from "node:fs";
import { createServer, request as httpRequest } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const mime = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8" };
const port = Number(process.env.REFLEX_PORT || 5173);
const host = process.env.REFLEX_FRONTEND_HOST || "0.0.0.0";
const apiOrigin = new URL(process.env.REFLEX_API_ORIGIN || "http://127.0.0.1:8000");

createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    const upstream = httpRequest({
      hostname: apiOrigin.hostname,
      port: apiOrigin.port || (apiOrigin.protocol === "https:" ? 443 : 80),
      protocol: apiOrigin.protocol,
      path: `${apiOrigin.pathname.replace(/\/$/, "")}${req.url.slice(4)}`,
      method: req.method,
      headers: { ...req.headers, host: apiOrigin.host },
    }, upstreamRes => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers); upstreamRes.pipe(res);
    });
    upstream.on("error", () => { res.writeHead(503, { "Content-Type": "application/json" }); res.end(JSON.stringify({ detail: "Reflex API is unavailable. Start the FastAPI backend and try again." })); });
    req.pipe(upstream); return;
  }
  const safePath = normalize(req.url === "/" ? "/index.html" : req.url.split("?")[0]).replace(/^([.][.][\\/])+/, "");
  const file = join(root, safePath);
  if (!file.startsWith(root) || !existsSync(file)) { res.writeHead(404); res.end("Not found"); return; }
  res.writeHead(200, { "Content-Type": mime[extname(file)] || "application/octet-stream" }); createReadStream(file).pipe(res);
}).listen(port, host, () => {
  console.log(`Reflex frontend: http://localhost:${port}`);
  console.log(`Network access: http://YOUR-COMPUTER-IP:${port}`);
  console.log(`API origin: ${apiOrigin.origin}`);
});
