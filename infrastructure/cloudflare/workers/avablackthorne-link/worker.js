addEventListener("fetch", event => {
  event.respondWith(handle(event.request, event));
});

addEventListener("queue", event => {
  event.waitUntil(deliverClickEvents(event));
});

const ATTRIBUTION_PATTERN = /^[A-Za-z0-9_-]{24,128}$/;
const HANDOFF_PURPOSE = "X_TELEGRAM_CTA_HANDOFF_V1";
const CLASSIFICATION_REASON = "VALID_FIRST_PARTY_HANDOFF_V1";
const CRAWLER_PATTERN = /(twitterbot|facebookexternalhit|slackbot|discordbot|telegrambot|googlebot|bingbot|duckduckbot|yandex|baiduspider|crawler|spider|preview|scanner|uptime|monitoring|headless)/i;

function bytes(value) {
  return new TextEncoder().encode(value);
}

function hex(buffer) {
  return Array.from(new Uint8Array(buffer), value => value.toString(16).padStart(2, "0")).join("");
}

async function sign(secret, value) {
  const key = await crypto.subtle.importKey(
    "raw", bytes(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  return hex(await crypto.subtle.sign("HMAC", key, bytes(value)));
}

function safeEqual(left, right) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

function likelyBrowser(req) {
  const userAgent = req.headers.get("user-agent") || "";
  return req.method === "GET" && Boolean(userAgent) && !CRAWLER_PATTERN.test(userAgent);
}

async function handoffProof(token, expiresAt) {
  if (typeof X_LINK_HANDOFF_SECRET !== "string" || X_LINK_HANDOFF_SECRET.length < 32) return "";
  const signature = await sign(
    X_LINK_HANDOFF_SECRET, `${HANDOFF_PURPOSE}.${token}.${expiresAt}`
  );
  return `${expiresAt}.${signature}`;
}

async function validHandoff(token, proof) {
  const [expiresRaw, signature, ...extra] = String(proof || "").split(".");
  if (extra.length || !/^\d+$/.test(expiresRaw || "") || !/^[a-f0-9]{64}$/.test(signature || "")) return false;
  const expiresAt = Number(expiresRaw);
  if (expiresAt < Math.floor(Date.now() / 1000) || expiresAt > Math.floor(Date.now() / 1000) + 600) return false;
  const expected = await handoffProof(token, expiresAt);
  return Boolean(expected) && safeEqual(expected, `${expiresAt}.${signature}`);
}

async function handle(req, event) {
  const url = new URL(req.url);

  const TELEGRAM_URL = "https://t.me/+zqVdLYlEbqc3M2Ix";
  const CARD_IMAGE = "https://ava-x-card.knphillips01.workers.dev/?v=2";

  // Keep the existing direct redirect endpoint.
  if (url.pathname === "/go") {
    const token = url.searchParams.get("p") || "";
    const proof = url.searchParams.get("h") || "";
    if (
      ATTRIBUTION_PATTERN.test(token)
      && likelyBrowser(req)
      && await validHandoff(token, proof)
      && typeof X_LINK_CLICKS !== "undefined"
    ) {
      const message = {
        eventId: crypto.randomUUID(),
        attributionToken: token,
        occurredAt: new Date().toISOString(),
        eventType: "X_TELEGRAM_CTA_HANDOFF",
        classification: "LIKELY_BROWSER",
        classificationReason: CLASSIFICATION_REASON,
        schemaVersion: 1
      };
      event.waitUntil(X_LINK_CLICKS.send(message));
    }
    return Response.redirect(TELEGRAM_URL, 302);
  }

  const attributionToken = url.searchParams.get("p") || "";
  let redirectPath = "/go";
  if (ATTRIBUTION_PATTERN.test(attributionToken) && likelyBrowser(req)) {
    const expiresAt = Math.floor(Date.now() / 1000) + 600;
    const proof = await handoffProof(attributionToken, expiresAt);
    if (proof) {
      redirectPath = `/go?p=${encodeURIComponent(attributionToken)}&h=${encodeURIComponent(proof)}`;
    }
  }

  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">

  <title>Ava Blackthorne</title>

  <!-- Open Graph -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://avablackthorne.com/">
  <meta property="og:title" content="Ava Blackthorne">
  <meta property="og:description" content="Come find me over here 💋">
  <meta property="og:image" content="${CARD_IMAGE}">
  <meta property="og:image:width" content="832">
  <meta property="og:image:height" content="1248">

  <!-- X / Twitter Card -->
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Ava Blackthorne">
  <meta name="twitter:description" content="Come find me over here 💋">
  <meta name="twitter:image" content="${CARD_IMAGE}">

  <style>
    :root {
      --bg: #0A0A0A;
      --text: #EAEAEA;
      --sub: #b1b5bb;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      text-align: center;
    }

    .status {
      padding: 30px;
    }

    h1 {
      margin: 0 0 10px;
      font-size: 2rem;
    }

    p {
      margin: 0;
      color: var(--sub);
    }
  </style>

  <script>
    window.addEventListener("DOMContentLoaded", function () {
      window.location.replace(${JSON.stringify(redirectPath)});
    });
  </script>
</head>

<body>
  <div class="status">
    <h1>Ava Blackthorne</h1>
    <p>Opening Telegram…</p>
  </div>
</body>
</html>`;

  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      // Never cache a browser-specific signed handoff. Unattributed card HTML
      // retains the production cache contract.
      "cache-control": ATTRIBUTION_PATTERN.test(attributionToken)
        ? "private, no-store"
        : "public, max-age=300"
    }
  });
}

async function deliverClickEvents(event) {
  for (const message of event.messages) {
    const body = JSON.stringify(message.body);
    const timestamp = String(Math.floor(Date.now() / 1000));
    const eventId = String(message.body.eventId || "");
    try {
      if (
        typeof X_LINK_INGESTION_SECRET !== "string"
        || X_LINK_INGESTION_SECRET.length < 32
        || typeof CREATOR_OS_INGEST_URL !== "string"
      ) throw new Error("X Link ingestion bindings are not configured.");
      const signature = await sign(
        X_LINK_INGESTION_SECRET, `${timestamp}.${eventId}.${body}`
      );
      const response = await fetch(CREATOR_OS_INGEST_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-X-Link-Timestamp": timestamp,
          "X-X-Link-Event-Id": eventId,
          "X-X-Link-Signature": `sha256=${signature}`
        },
        body
      });
      if (response.ok || (response.status >= 400 && response.status < 500 && response.status !== 429)) {
        message.ack();
      } else {
        message.retry();
      }
    } catch (_error) {
      message.retry();
    }
  }
}
