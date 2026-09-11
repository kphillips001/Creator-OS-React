const assert = require("node:assert/strict");
const path = require("node:path");

const listeners = {};
global.addEventListener = (name, callback) => { listeners[name] = callback; };
global.X_LINK_HANDOFF_SECRET = "handoff-test-secret-that-is-at-least-32-bytes";
global.X_LINK_INGESTION_SECRET = "ingestion-test-secret-that-is-at-least-32-bytes";
global.CREATOR_OS_INGEST_URL = "https://hooks.example.test/events";
const queued = [];
global.X_LINK_CLICKS = { send: async (message) => { queued.push(message); } };
require(path.resolve(__dirname, "../infrastructure/cloudflare/workers/avablackthorne-link/worker.js"));

const TOKEN = "opaque_token_12345678901234567890";
const browserHeaders = { "user-agent": "Mozilla/5.0 certification" };
const crawlerHeaders = { "user-agent": "Twitterbot/1.0" };

async function request(url, headers = browserHeaders) {
  let responsePromise;
  const waits = [];
  listeners.fetch({
    request: new Request(url, { headers }),
    respondWith(value) { responsePromise = Promise.resolve(value); },
    waitUntil(value) { waits.push(Promise.resolve(value)); },
  });
  const response = await responsePromise;
  return { response, waits };
}

(async () => {
  const plain = await request("https://avablackthorne.com/me");
  const plainHtml = await plain.response.text();
  const attributed = await request(`https://avablackthorne.com/me?p=${TOKEN}`);
  const attributedHtml = await attributed.response.text();

  for (const metadata of [
    '<meta name="twitter:card" content="summary">',
    '<meta name="twitter:title" content="Ava Blackthorne">',
    '<meta name="twitter:description" content="Come find me over here 💋">',
    'https://ava-x-card.knphillips01.workers.dev/?v=2',
  ]) {
    assert.ok(plainHtml.includes(metadata));
    assert.ok(attributedHtml.includes(metadata));
  }
  assert.equal(queued.length, 0, "raw /me must not enqueue an event");

  const handoff = attributedHtml.match(/window\.location\.replace\("([^\"]+)"\)/)[1];
  const valid = await request(`https://avablackthorne.com${handoff}`);
  assert.equal(valid.response.status, 302);
  assert.equal(valid.response.headers.get("location"), "https://t.me/+zqVdLYlEbqc3M2Ix");
  await Promise.all(valid.waits);
  assert.equal(queued.length, 1);
  assert.deepEqual(Object.keys(queued[0]).sort(), [
    "attributionToken", "classification", "classificationReason", "eventId",
    "eventType", "occurredAt", "schemaVersion",
  ]);
  assert.equal(queued[0].attributionToken, TOKEN);
  assert.equal(queued[0].classification, "LIKELY_BROWSER");

  await request(`https://avablackthorne.com/go?p=${TOKEN}&h=1.${"0".repeat(64)}`);
  assert.equal(queued.length, 1, "expired proof must not enqueue");
  await request(`https://avablackthorne.com/go?p=${TOKEN}&h=9999999999.${"0".repeat(64)}`);
  assert.equal(queued.length, 1, "invalid proof must not enqueue");
  const direct = await request("https://avablackthorne.com/go");
  assert.equal(direct.response.status, 302);
  assert.equal(queued.length, 1, "direct /go must not enqueue");

  const crawler = await request(`https://avablackthorne.com/me?p=${TOKEN}`, crawlerHeaders);
  const crawlerHtml = await crawler.response.text();
  assert.ok(crawlerHtml.includes('<meta name="twitter:card" content="summary">'));
  assert.ok(crawlerHtml.includes('window.location.replace("/go")'));

  global.X_LINK_CLICKS.send = async () => { throw new Error("queue unavailable"); };
  const failedQueue = await request(`https://avablackthorne.com${handoff}`);
  assert.equal(failedQueue.response.status, 302, "queue failure must not block redirect");
  await Promise.allSettled(failedQueue.waits);

  let retried = 0;
  let acknowledged = 0;
  let deliveredBody = "";
  global.fetch = async (_url, options) => {
    deliveredBody = options.body;
    return new Response("unavailable", { status: 503 });
  };
  let consumerWork;
  const queuedEvent = { ...queued[0], eventId: "stable-event-id" };
  listeners.queue({
    messages: [{
      body: queuedEvent,
      ack() { acknowledged += 1; },
      retry() { retried += 1; },
    }],
    waitUntil(value) { consumerWork = Promise.resolve(value); },
  });
  await consumerWork;
  assert.equal(retried, 1);
  assert.equal(acknowledged, 0);
  assert.equal(JSON.parse(deliveredBody).eventId, "stable-event-id");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
