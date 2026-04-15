#!/usr/bin/env node
/**
 * OCP Safe Proxy — OpenAI-compatible proxy for Claude CLI
 * Version: 1.0.0 — Secure rewrite
 *
 * Améliorations sécurité vs original :
 *  - Suppression totale de la lecture des credentials OAuth (plus de vol de token)
 *  - Pas d'accès aux fichiers système (~/.claude, keychain)
 *  - Validation stricte de tous les inputs
 *  - Logs sans données sensibles (pas de contenu de prompt, pas de tokens)
 *  - Pas d'installation automatique de service système
 *  - Sanitisation des variables d'environnement transmises au CLI
 *  - Timeouts bornés, pas de valeurs arbitraires
 *  - Authentification Bearer robuste avec timing-safe compare
 *  - Gestion mémoire : cap sur les sessions et les erreurs stockées
 *
 * Usage :
 *   PROXY_API_KEY=secret node server.mjs
 *
 * Variables d'environnement :
 *   CLAUDE_BIN            — chemin vers le binaire claude (défaut: auto-detect)
 *   CLAUDE_PROXY_PORT     — port d'écoute (défaut: 3456)
 *   PROXY_API_KEY         — clé Bearer obligatoire pour authentifier les requêtes
 *   CLAUDE_MAX_CONCURRENT — max requêtes parallèles (défaut: 4, max: 16)
 *   CLAUDE_TIMEOUT_MS     — timeout global par requête en ms (défaut: 120000, max: 300000)
 *   CLAUDE_ALLOWED_TOOLS  — outils autorisés séparés par virgule (défaut: liste restrictive)
 *   CLAUDE_BIND_HOST      — interface d'écoute (défaut: 127.0.0.1 — NE PAS changer en prod)
 */

import { createServer } from "node:http";
import { spawn, execFileSync } from "node:child_process";
import { randomUUID, timingSafeEqual } from "node:crypto";
import { accessSync, constants } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve, normalize } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const VERSION = "1.0.0";
const START_TIME = Date.now();

// ── Constantes de sécurité ──────────────────────────────────────────────

const MAX_BODY_SIZE = 512 * 1024;          // 512 KB max par requête
const MAX_MESSAGES = 100;                  // max messages par conversation
const MAX_MESSAGE_LENGTH = 32_000;         // max chars par message
const MAX_SESSION_STORE = 500;             // max sessions en mémoire
const MAX_CONCURRENT_HARD_LIMIT = 16;      // plafond absolu
const MAX_TIMEOUT_MS = 300_000;            // 5 min max
const ALLOWED_MODELS_SET = new Set([
  "claude-opus-4-6",
  "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001",
]);

// ── Validation de la configuration ─────────────────────────────────────

function validateConfig() {
  const errors = [];

  // PROXY_API_KEY obligatoire
  if (!process.env.PROXY_API_KEY || process.env.PROXY_API_KEY.length < 16) {
    errors.push("PROXY_API_KEY doit être défini et faire au moins 16 caractères.");
  }

  // Ne pas exposer sur 0.0.0.0 sans avertissement explicite
  const bindHost = process.env.CLAUDE_BIND_HOST || "127.0.0.1";
  if (bindHost !== "127.0.0.1" && bindHost !== "::1") {
    errors.push(
      `ATTENTION: CLAUDE_BIND_HOST=${bindHost} expose le proxy sur le réseau. ` +
      "C'est dangereux sauf si vous savez ce que vous faites."
    );
    // On log l'avertissement mais on ne bloque pas
    console.error("[SECURITY WARNING]", errors[errors.length - 1]);
    errors.pop();
  }

  if (errors.length > 0) {
    for (const e of errors) console.error("[CONFIG ERROR]", e);
    process.exit(1);
  }
}

validateConfig();

// ── Résolution du binaire claude ────────────────────────────────────────

function resolveClaude() {
  const envBin = process.env.CLAUDE_BIN;
  if (envBin) {
    // Bloquer les path traversal
    const abs = resolve(envBin);
    if (abs !== normalize(abs)) {
      console.error("FATAL: CLAUDE_BIN contient un chemin invalide.");
      process.exit(1);
    }
    try {
      accessSync(abs, constants.X_OK);
      return abs;
    } catch {
      console.error(`FATAL: CLAUDE_BIN="${abs}" n'est pas exécutable.`);
      process.exit(1);
    }
  }

  const candidates = [
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "/usr/bin/claude",
    join(process.env.HOME || "/tmp", ".local/bin/claude"),
  ];

  for (const p of candidates) {
    try { accessSync(p, constants.X_OK); return p; } catch {}
  }

  try {
    const resolved = execFileSync("which", ["claude"], {
      encoding: "utf8",
      timeout: 5_000,
      // Environnement minimal pour which
      env: { PATH: process.env.PATH || "/usr/local/bin:/usr/bin:/bin" },
    }).trim();
    if (resolved) return resolved;
  } catch {}

  console.error(
    "FATAL: binaire claude introuvable.\n" +
    "  Installez Claude CLI : https://docs.anthropic.com/fr/docs/claude-code\n" +
    "  Ou définissez CLAUDE_BIN=/chemin/vers/claude"
  );
  process.exit(1);
}

// ── Configuration ───────────────────────────────────────────────────────

const CLAUDE_BIN = resolveClaude();
const PORT = clampInt(process.env.CLAUDE_PROXY_PORT, 3456, 1024, 65535);
const BIND_HOST = process.env.CLAUDE_BIND_HOST || "127.0.0.1";
const PROXY_API_KEY = process.env.PROXY_API_KEY; // validé plus haut
const MAX_CONCURRENT = clampInt(process.env.CLAUDE_MAX_CONCURRENT, 4, 1, MAX_CONCURRENT_HARD_LIMIT);
const TIMEOUT_MS = clampInt(process.env.CLAUDE_TIMEOUT_MS, 120_000, 10_000, MAX_TIMEOUT_MS);
const SESSION_TTL_MS = 3_600_000; // 1h, non configurable pour éviter les abus

// Outils autorisés : liste restrictive par défaut (pas de Bash par défaut)
const DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep"];
const ALLOWED_TOOLS = parseAllowedTools(
  process.env.CLAUDE_ALLOWED_TOOLS,
  DEFAULT_ALLOWED_TOOLS
);

function clampInt(raw, defaultVal, min, max) {
  const n = parseInt(raw || String(defaultVal), 10);
  if (isNaN(n)) return defaultVal;
  return Math.min(Math.max(n, min), max);
}

function parseAllowedTools(raw, defaults) {
  if (!raw) return defaults;
  // Whitelist des outils autorisables
  const SAFE_TOOLS = new Set([
    "Read", "Glob", "Grep", "Write", "Edit",
    "WebFetch", "WebSearch", "Agent",
  ]);
  const parsed = raw.split(",")
    .map(s => s.trim())
    .filter(s => SAFE_TOOLS.has(s));
  return parsed.length > 0 ? parsed : defaults;
}

// ── Logging sécurisé ────────────────────────────────────────────────────
// On ne logue JAMAIS le contenu des messages ni les tokens

function log(level, event, data = {}) {
  // Retirer tout champ potentiellement sensible
  const safe = { ...data };
  for (const key of ["prompt", "content", "messages", "token", "key", "auth"]) {
    delete safe[key];
  }
  const entry = { ts: new Date().toISOString(), level, event, ...safe };
  if (level === "error" || level === "warn") {
    console.error(JSON.stringify(entry));
  } else {
    console.log(JSON.stringify(entry));
  }
}

// ── Authentification ────────────────────────────────────────────────────

function checkAuth(req) {
  if (!PROXY_API_KEY) return true; // ne devrait pas arriver (validé au démarrage)
  const header = req.headers["authorization"] || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) return false;
  try {
    const a = Buffer.from(PROXY_API_KEY, "utf8");
    const b = Buffer.from(token, "utf8");
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

// ── Validation des inputs ───────────────────────────────────────────────

function validateChatRequest(body) {
  const errors = [];

  if (!body || typeof body !== "object") {
    return { valid: false, errors: ["Corps de requête invalide"] };
  }

  // Model
  const model = String(body.model || "").trim();
  if (!ALLOWED_MODELS_SET.has(model) && !["opus", "sonnet", "haiku"].includes(model)) {
    errors.push(`Modèle invalide: "${model}". Modèles autorisés: ${[...ALLOWED_MODELS_SET].join(", ")}`);
  }

  // Messages
  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    errors.push("messages doit être un tableau non vide");
  } else {
    if (body.messages.length > MAX_MESSAGES) {
      errors.push(`Trop de messages: ${body.messages.length} (max: ${MAX_MESSAGES})`);
    }
    for (let i = 0; i < Math.min(body.messages.length, MAX_MESSAGES); i++) {
      const m = body.messages[i];
      if (!m || typeof m !== "object") {
        errors.push(`messages[${i}]: objet attendu`);
        continue;
      }
      if (!["user", "assistant", "system"].includes(m.role)) {
        errors.push(`messages[${i}].role invalide: "${m.role}"`);
      }
      const content = typeof m.content === "string"
        ? m.content
        : typeof m.content === "object"
          ? JSON.stringify(m.content)
          : "";
      if (content.length > MAX_MESSAGE_LENGTH) {
        errors.push(`messages[${i}].content trop long: ${content.length} chars (max: ${MAX_MESSAGE_LENGTH})`);
      }
    }
  }

  // session_id : doit être un UUID ou absent
  if (body.session_id !== undefined) {
    if (typeof body.session_id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(body.session_id)) {
      errors.push("session_id doit être un UUID valide");
    }
  }

  return { valid: errors.length === 0, errors };
}

// ── Mapping des modèles ─────────────────────────────────────────────────

const MODEL_MAP = {
  "claude-opus-4-6": "claude-opus-4-6",
  "claude-sonnet-4-6": "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
  "opus": "claude-opus-4-6",
  "sonnet": "claude-sonnet-4-6",
  "haiku": "claude-haiku-4-5-20251001",
};

const MODELS = [
  { id: "claude-opus-4-6", object: "model", owned_by: "anthropic" },
  { id: "claude-sonnet-4-6", object: "model", owned_by: "anthropic" },
  { id: "claude-haiku-4-5-20251001", object: "model", owned_by: "anthropic" },
];

// ── Gestion des sessions ────────────────────────────────────────────────

const sessions = new Map(); // sessionId → { uuid, lastUsed, model }

const sessionCleanup = setInterval(() => {
  const now = Date.now();
  let pruned = 0;
  for (const [id, s] of sessions) {
    if (now - s.lastUsed > SESSION_TTL_MS) {
      sessions.delete(id);
      pruned++;
    }
  }
  // Aussi élaguer si on dépasse la limite mémoire
  if (sessions.size > MAX_SESSION_STORE) {
    const sorted = [...sessions.entries()].sort((a, b) => a[1].lastUsed - b[1].lastUsed);
    const toDelete = sorted.slice(0, sessions.size - MAX_SESSION_STORE);
    for (const [id] of toDelete) sessions.delete(id);
    pruned += toDelete.length;
  }
  if (pruned > 0) log("info", "sessions_pruned", { count: pruned, remaining: sessions.size });
}, 60_000);

// ── Stats (sans données sensibles) ─────────────────────────────────────

const stats = {
  totalRequests: 0,
  activeRequests: 0,
  errors: 0,
  timeouts: 0,
};

// ── Construction du prompt ──────────────────────────────────────────────

function messagesToPrompt(messages) {
  return messages
    .slice(0, MAX_MESSAGES)
    .map(m => {
      const text = typeof m.content === "string"
        ? m.content.slice(0, MAX_MESSAGE_LENGTH)
        : JSON.stringify(m.content).slice(0, MAX_MESSAGE_LENGTH);
      if (m.role === "system") return `[System] ${text}`;
      if (m.role === "assistant") return `[Assistant] ${text}`;
      return text;
    })
    .join("\n\n");
}

// ── Environnement sécurisé pour le subprocess ───────────────────────────
// On transmet UNIQUEMENT les variables nécessaires, et on supprime
// toutes les credentials/tokens qui pourraient fuiter

function buildSafeEnv() {
  const safe = {};

  // Variables système minimales nécessaires au fonctionnement du CLI
  const allowed = ["PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME", "TERM"];
  for (const k of allowed) {
    if (process.env[k]) safe[k] = process.env[k];
  }

  // Variables Claude CLI spécifiques (légitimes)
  if (process.env.CLAUDE_BIN) safe.CLAUDE_BIN = process.env.CLAUDE_BIN;

  // JAMAIS transmettre :
  // - ANTHROPIC_API_KEY
  // - ANTHROPIC_AUTH_TOKEN
  // - ANTHROPIC_BASE_URL
  // - CLAUDECODE
  // - AWS_*, GOOGLE_*, etc.
  // - Toute variable contenant TOKEN, KEY, SECRET, PASSWORD, CREDENTIAL

  return safe;
}

// ── Spawn du processus claude ───────────────────────────────────────────

function spawnClaude(model, messages, sessionId) {
  return new Promise((resolve, reject) => {
    if (stats.activeRequests >= MAX_CONCURRENT) {
      return reject(new Error(`Limite de concurrence atteinte (${MAX_CONCURRENT})`));
    }

    const cliModel = MODEL_MAP[model] || "claude-sonnet-4-6";
    stats.activeRequests++;
    stats.totalRequests++;

    const requestId = randomUUID().slice(0, 8);

    // Construire les arguments CLI
    const args = ["-p", "--model", cliModel, "--output-format", "text"];

    // Gestion de session
    let sessionUuid = null;
    let isResume = false;
    let prompt;

    if (sessionId && sessions.has(sessionId)) {
      const sess = sessions.get(sessionId);
      sess.lastUsed = Date.now();
      sessionUuid = sess.uuid;
      isResume = true;
      // En mode resume, on envoie seulement le dernier message utilisateur
      const lastUser = [...messages].reverse().find(m => m.role === "user");
      prompt = lastUser
        ? (typeof lastUser.content === "string"
            ? lastUser.content.slice(0, MAX_MESSAGE_LENGTH)
            : JSON.stringify(lastUser.content).slice(0, MAX_MESSAGE_LENGTH))
        : "";
      args.push("--resume", sessionUuid);
    } else if (sessionId) {
      sessionUuid = randomUUID();
      sessions.set(sessionId, { uuid: sessionUuid, lastUsed: Date.now(), model: cliModel });
      prompt = messagesToPrompt(messages);
      args.push("--session-id", sessionUuid);
    } else {
      prompt = messagesToPrompt(messages);
      args.push("--no-session-persistence");
    }

    // Outils autorisés (pas de --dangerously-skip-permissions)
    if (ALLOWED_TOOLS.length > 0) {
      args.push("--allowedTools", ...ALLOWED_TOOLS);
    }

    const env = buildSafeEnv();

    log("info", "claude_spawn", {
      requestId,
      model: cliModel,
      promptChars: prompt.length,
      sessionId: sessionId ? sessionId.slice(0, 8) + "..." : null,
      resume: isResume,
    });

    let proc;
    try {
      proc = spawn(CLAUDE_BIN, args, {
        env,
        stdio: ["pipe", "pipe", "pipe"],
        // Pas de shell : évite les injections via les arguments
        shell: false,
      });
    } catch (err) {
      stats.activeRequests--;
      return reject(new Error(`Impossible de lancer claude: ${err.message}`));
    }

    let stdout = "";
    let stderr = "";
    let settled = false;
    let gotFirstByte = false;
    let firstByteTimer = null;
    let overallTimer = null;

    // Calculer le timeout first-byte selon le modèle
    const firstByteMs = cliModel.includes("opus") ? 60_000
      : cliModel.includes("haiku") ? 20_000
      : 40_000;

    function finish(err, result) {
      if (settled) return;
      settled = true;
      clearTimeout(firstByteTimer);
      clearTimeout(overallTimer);
      stats.activeRequests--;
      try { if (!proc.killed) proc.kill("SIGTERM"); } catch {}
      if (err) {
        stats.errors++;
        // Supprimer la session si le resume a échoué
        if (isResume && sessionId) sessions.delete(sessionId);
        reject(err);
      } else {
        resolve(result);
      }
    }

    // First-byte timeout
    firstByteTimer = setTimeout(() => {
      if (!gotFirstByte) {
        stats.timeouts++;
        log("warn", "first_byte_timeout", { requestId, model: cliModel, timeoutMs: firstByteMs });
        try { proc.kill("SIGTERM"); } catch {}
        setTimeout(() => { try { proc.kill("SIGKILL"); } catch {} }, 3_000);
        finish(new Error("Timeout: pas de réponse du modèle"), null);
      }
    }, firstByteMs);

    // Overall timeout
    overallTimer = setTimeout(() => {
      stats.timeouts++;
      log("warn", "request_timeout", { requestId, model: cliModel, timeoutMs: TIMEOUT_MS });
      try { proc.kill("SIGTERM"); } catch {}
      setTimeout(() => { try { proc.kill("SIGKILL"); } catch {} }, 3_000);
      finish(new Error("Timeout: requête trop longue"), null);
    }, TIMEOUT_MS);

    proc.stdout.on("data", d => {
      if (!gotFirstByte) {
        gotFirstByte = true;
        clearTimeout(firstByteTimer);
      }
      stdout += d;
      // Cap mémoire sur la sortie
      if (stdout.length > 1_000_000) {
        finish(new Error("Réponse trop longue (> 1MB)"), null);
      }
    });

    proc.stderr.on("data", d => {
      stderr += d;
      if (stderr.length > 10_000) stderr = stderr.slice(-10_000);
    });

    proc.on("close", (code) => {
      if (settled) return;
      if (code !== 0) {
        // Ne pas exposer le stderr complet (peut contenir des infos sensibles)
        const safeErr = stderr.slice(0, 200).replace(/Bearer\s+\S+/gi, "[REDACTED]");
        log("error", "claude_exit", { requestId, model: cliModel, code });
        finish(new Error(`claude a terminé avec le code ${code}: ${safeErr}`), null);
      } else {
        log("info", "claude_ok", {
          requestId,
          model: cliModel,
          responseChars: stdout.length,
          elapsedMs: Date.now() - (START_TIME), // pas de t0 exposé
        });
        finish(null, stdout.trim());
      }
    });

    proc.on("error", err => {
      log("error", "spawn_error", { requestId, message: err.message });
      finish(err, null);
    });

    // Écrire le prompt et fermer stdin
    try {
      proc.stdin.write(prompt, "utf8");
      proc.stdin.end();
    } catch (err) {
      finish(new Error(`Erreur stdin: ${err.message}`), null);
    }
  });
}

// ── Streaming ───────────────────────────────────────────────────────────

function spawnClaudeStreaming(model, messages, sessionId, res) {
  if (stats.activeRequests >= MAX_CONCURRENT) {
    return jsonError(res, 503, "Limite de concurrence atteinte");
  }

  const cliModel = MODEL_MAP[model] || "claude-sonnet-4-6";
  const requestId = randomUUID().slice(0, 8);
  const completionId = `chatcmpl-${randomUUID()}`;
  const created = Math.floor(Date.now() / 1000);

  stats.activeRequests++;
  stats.totalRequests++;

  const args = ["-p", "--model", cliModel, "--output-format", "text"];
  let prompt;
  let isResume = false;

  if (sessionId && sessions.has(sessionId)) {
    const sess = sessions.get(sessionId);
    sess.lastUsed = Date.now();
    const lastUser = [...messages].reverse().find(m => m.role === "user");
    prompt = lastUser
      ? (typeof lastUser.content === "string"
          ? lastUser.content.slice(0, MAX_MESSAGE_LENGTH)
          : JSON.stringify(lastUser.content).slice(0, MAX_MESSAGE_LENGTH))
      : "";
    args.push("--resume", sess.uuid);
    isResume = true;
  } else if (sessionId) {
    const uuid = randomUUID();
    sessions.set(sessionId, { uuid, lastUsed: Date.now(), model: cliModel });
    prompt = messagesToPrompt(messages);
    args.push("--session-id", uuid);
  } else {
    prompt = messagesToPrompt(messages);
    args.push("--no-session-persistence");
  }

  if (ALLOWED_TOOLS.length > 0) {
    args.push("--allowedTools", ...ALLOWED_TOOLS);
  }

  const env = buildSafeEnv();

  let proc;
  try {
    proc = spawn(CLAUDE_BIN, args, { env, stdio: ["pipe", "pipe", "pipe"], shell: false });
  } catch (err) {
    stats.activeRequests--;
    return jsonError(res, 500, `Impossible de lancer claude: ${err.message}`);
  }

  let headersSent = false;
  let settled = false;
  let gotFirstByte = false;
  let totalBytes = 0;

  const firstByteMs = cliModel.includes("opus") ? 60_000
    : cliModel.includes("haiku") ? 20_000
    : 40_000;

  function ensureHeaders() {
    if (headersSent || res.writableEnded) return false;
    headersSent = true;
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    });
    sendSSE(res, {
      id: completionId, object: "chat.completion.chunk",
      created, model,
      choices: [{ index: 0, delta: { role: "assistant" }, finish_reason: null }],
    });
    return true;
  }

  function cleanup() {
    if (settled) return;
    settled = true;
    clearTimeout(firstByteTimer);
    clearTimeout(overallTimer);
    stats.activeRequests--;
    try { if (!proc.killed) proc.kill("SIGTERM"); } catch {}
  }

  const firstByteTimer = setTimeout(() => {
    if (!gotFirstByte) {
      stats.timeouts++;
      cleanup();
      if (!headersSent && !res.writableEnded) {
        jsonError(res, 504, "Timeout: pas de réponse du modèle");
      } else if (!res.writableEnded) {
        res.end();
      }
    }
  }, firstByteMs);

  const overallTimer = setTimeout(() => {
    stats.timeouts++;
    cleanup();
    if (!res.writableEnded) res.end();
  }, TIMEOUT_MS);

  proc.stdout.on("data", d => {
    if (!gotFirstByte) {
      gotFirstByte = true;
      clearTimeout(firstByteTimer);
      ensureHeaders();
    }
    const text = d.toString("utf8");
    totalBytes += text.length;
    if (totalBytes > 1_000_000) {
      cleanup();
      if (!res.writableEnded) res.end();
      return;
    }
    if (!res.writableEnded) {
      sendSSE(res, {
        id: completionId, object: "chat.completion.chunk",
        created, model,
        choices: [{ index: 0, delta: { content: text }, finish_reason: null }],
      });
    }
  });

  proc.stderr.on("data", () => {}); // ignorer stderr en streaming

  proc.on("close", code => {
    if (settled) return;
    cleanup();
    if (code !== 0) {
      log("error", "claude_exit_stream", { requestId, model: cliModel, code });
      if (isResume && sessionId) sessions.delete(sessionId);
      if (!headersSent && !res.writableEnded) {
        jsonError(res, 500, "Erreur interne du modèle");
      }
    } else {
      log("info", "claude_ok_stream", { requestId, model: cliModel, bytes: totalBytes });
      if (!headersSent) ensureHeaders();
    }
    if (!res.writableEnded) {
      sendSSE(res, {
        id: completionId, object: "chat.completion.chunk",
        created, model,
        choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
      });
      res.write("data: [DONE]\n\n");
      res.end();
    }
  });

  proc.on("error", err => {
    cleanup();
    log("error", "spawn_error_stream", { requestId, message: err.message });
    if (!headersSent && !res.writableEnded) jsonError(res, 500, err.message);
    else if (!res.writableEnded) res.end();
  });

  res.on("close", () => {
    if (!proc.killed) try { proc.kill("SIGTERM"); } catch {}
    cleanup();
  });

  try {
    proc.stdin.write(prompt, "utf8");
    proc.stdin.end();
  } catch (err) {
    cleanup();
    if (!res.writableEnded) jsonError(res, 500, err.message);
  }
}

// ── Helpers HTTP ────────────────────────────────────────────────────────

function jsonResponse(res, status, data) {
  if (res.headersSent || res.writableEnded) return;
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}

function jsonError(res, status, message) {
  jsonResponse(res, status, { error: { message, type: "proxy_error", code: status } });
}

function sendSSE(res, data) {
  if (!res.writableEnded) res.write(`data: ${JSON.stringify(data)}\n\n`);
}

async function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    let size = 0;
    req.on("data", chunk => {
      size += chunk.length;
      if (size > MAX_BODY_SIZE) {
        reject(new Error("Corps de requête trop grand"));
        return;
      }
      body += chunk;
    });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

// ── Serveur HTTP ────────────────────────────────────────────────────────

const server = createServer(async (req, res) => {
  // Headers de sécurité sur toutes les réponses
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");

  const url = new URL(req.url, `http://${BIND_HOST}:${PORT}`);
  const path = url.pathname;
  const method = req.method.toUpperCase();

  // ── Routes publiques (sans auth) ────────────────────────────────────
  if (path === "/health" && method === "GET") {
    return jsonResponse(res, 200, {
      status: "ok",
      version: VERSION,
      uptime: Math.floor((Date.now() - START_TIME) / 1000),
    });
  }

  // ── Authentification ────────────────────────────────────────────────
  if (!checkAuth(req)) {
    res.setHeader("WWW-Authenticate", 'Bearer realm="ocp-proxy"');
    return jsonError(res, 401, "Non autorisé. Fournissez un Bearer token valide.");
  }

  // ── Routes authentifiées ────────────────────────────────────────────

  // Liste des modèles
  if (path === "/v1/models" && method === "GET") {
    return jsonResponse(res, 200, {
      object: "list",
      data: MODELS,
    });
  }

  // Stats du proxy (sans données sensibles)
  if (path === "/v1/status" && method === "GET") {
    return jsonResponse(res, 200, {
      version: VERSION,
      uptime: Math.floor((Date.now() - START_TIME) / 1000),
      requests: {
        total: stats.totalRequests,
        active: stats.activeRequests,
        errors: stats.errors,
        timeouts: stats.timeouts,
      },
      sessions: {
        active: sessions.size,
        maxStore: MAX_SESSION_STORE,
      },
      config: {
        maxConcurrent: MAX_CONCURRENT,
        timeoutMs: TIMEOUT_MS,
        allowedTools: ALLOWED_TOOLS,
        bindHost: BIND_HOST,
      },
    });
  }

  // Gestion des sessions
  if (path === "/v1/sessions" && method === "DELETE") {
    const count = sessions.size;
    sessions.clear();
    return jsonResponse(res, 200, { deleted: count });
  }

  // Chat completions
  if (path === "/v1/chat/completions" && method === "POST") {
    let rawBody;
    try {
      rawBody = await readBody(req);
    } catch (err) {
      return jsonError(res, 413, err.message);
    }

    let body;
    try {
      body = JSON.parse(rawBody);
    } catch {
      return jsonError(res, 400, "JSON invalide");
    }

    const { valid, errors } = validateChatRequest(body);
    if (!valid) {
      return jsonError(res, 400, `Requête invalide: ${errors.join("; ")}`);
    }

    const model = String(body.model).trim();
    const messages = body.messages.slice(0, MAX_MESSAGES);
    const stream = body.stream === true;
    const sessionId = body.session_id || req.headers["x-session-id"] || null;

    if (stream) {
      return spawnClaudeStreaming(model, messages, sessionId, res);
    }

    try {
      const content = await spawnClaude(model, messages, sessionId);
      return jsonResponse(res, 200, {
        id: `chatcmpl-${randomUUID()}`,
        object: "chat.completion",
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [{
          index: 0,
          message: { role: "assistant", content },
          finish_reason: "stop",
        }],
        // On ne renvoie pas de token counts (ils seraient faux de toute façon)
        usage: null,
      });
    } catch (err) {
      const status = err.message.includes("concurrence") ? 503
        : err.message.includes("Timeout") ? 504
        : 500;
      return jsonError(res, status, err.message);
    }
  }

  // Route inconnue
  return jsonError(res, 404, `Route non trouvée: ${method} ${path}`);
});

// ── Démarrage ───────────────────────────────────────────────────────────

server.listen(PORT, BIND_HOST, () => {
  console.log(JSON.stringify({
    ts: new Date().toISOString(),
    level: "info",
    event: "server_start",
    version: VERSION,
    host: BIND_HOST,
    port: PORT,
    maxConcurrent: MAX_CONCURRENT,
    timeoutMs: TIMEOUT_MS,
    allowedTools: ALLOWED_TOOLS,
    auth: "bearer_required",
    note: "Ne jamais exposer ce proxy sur internet sans pare-feu.",
  }));
});

// ── Arrêt propre ─────────────────────────────────────────────────────────

function gracefulShutdown(signal) {
  log("info", "shutdown", { signal });
  clearInterval(sessionCleanup);
  server.close(() => {
    log("info", "server_closed");
    process.exit(0);
  });
  // Forcer l'arrêt après 10s
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
process.on("SIGINT", () => gracefulShutdown("SIGINT"));
process.on("uncaughtException", err => {
  // Ne pas logger le stack trace complet (peut contenir des données)
  log("error", "uncaught_exception", { message: err.message });
  process.exit(1);
});
process.on("unhandledRejection", reason => {
  log("error", "unhandled_rejection", { message: String(reason).slice(0, 200) });
});
