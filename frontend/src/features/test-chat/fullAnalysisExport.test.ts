import { describe, expect, it } from "vitest";

import type { LiveControlledSnapshot } from "../../infrastructure/api/testChatApi";
import { buildFullAnalysis, redactObserverSnapshot, serializeDiagnostic } from "./fullAnalysisExport";

const snapshot = {
  mode: "LIVE_CONTROLLED_TEST", badges: [], configured: true, readOnly: true, pollIntervalSeconds: 3,
  customer: { telegramNumericId: "12******90", mappingState: "UNMAPPED" }, conversation: [],
  turns: [
    { turn: 1, customerMessage: "Hello", customerMessagePersisted: true, reply: "Hey there", operationId: "op-1", decision: { intent: "LOW", commercialSummary: { customerTemperature: { state: "COLD" }, policyGate: { controllingGate: "NONE" } }, recommendation: { candidates: [{ id: "offer-1", score: 0.4 }] } } },
    { turn: 2, customerMessage: "Unavailable", customerMessagePersisted: false, reply: "Older reply", operationId: "op-2", decision: { intent: "HIGH", sell: false } },
  ],
  currentState: { stage: "WARM_UP" }, recommendationDecision: { selected: null }, commerceState: { purchaseIntent: null },
  memory: { source: "DURABLE" }, timeContext: { timezone: "America/Chicago" }, pacing: { applied: false },
  ordinaryReplyOperations: [{ operationId: "op-1", telegramAccountScope: "AVA_TELETHON_PRIVATE", nested: [[{ state: "SENT_CONFIRMED" }]] }],
  identityDiagnostics: { mapping: null }, fingerprintDiagnostics: { reservation: null }, sessionDiagnostics: { session: null },
  purchaseAcknowledgement: { sent: false }, controlledTestOffering: { basePriceMinor: 300 },
  runtimeSafety: { global: "BLOCKED", apiHash: "must-not-leak", nestedFutureDiagnostic: { safeValue: 42, auth_key: "also-secret" } },
  resetDryRun: { allowed: false, executed: false, blockers: ["turn exists"], wouldClear: {}, wouldPreserve: [] },
} as unknown as LiveControlledSnapshot;

describe("full controlled analysis export", () => {
  it("exports every section, every turn, nested diagnostics, and the raw safe snapshot", () => {
    const output = buildFullAnalysis(snapshot, new Date("2026-08-26T12:00:00Z"));
    ["Controlled Customer", "Conversation", "Decision Timeline", "Current Sales Brain State", "Recommendation Decision",
      "Commerce State", "Memory Diagnostics", "Time Context", "Response Pacing", "Ordinary Reply Operations",
      "Identity Diagnostics", "Fingerprint Diagnostics", "Session Diagnostics", "Purchase Acknowledgement",
      "Controlled Test Offering", "Runtime Safety", "Raw Safe Observer Snapshot"].forEach((title) => expect(output).toContain(`## ${title}`));
    expect(output).toMatch(/Decision Summary.*Turn 1/);
    expect(output).toMatch(/Decision Summary.*Turn 2/);
    expect(output).toMatch(/Commercial Summary.*Turn 1/);
    expect(output).toContain("controllingGate: NONE");
    expect(output).toContain("predates durable inbound capture");
    expect(output).toContain("nestedFutureDiagnostic");
    expect(output).toContain("safeValue");
    expect(output).toContain("SENT_CONFIRMED");
    expect(output).not.toContain("[object Object]");
    expect(output).not.toContain("must-not-leak");
    expect(output).not.toContain("also-secret");
  });

  it("recursively serializes nested diagnostics and redacts secret-shaped fields", () => {
    expect(serializeDiagnostic({ candidates: [[{ id: "one" }]] })).toContain("id: one");
    const safe = redactObserverSnapshot({ api_hash: "one", phoneCodeHash: "two", child: { password: "three", okay: "visible" } });
    expect(JSON.stringify(safe)).not.toMatch(/:"(one|two|three)"/);
    expect(JSON.stringify(safe)).toContain("visible");
  });
});
