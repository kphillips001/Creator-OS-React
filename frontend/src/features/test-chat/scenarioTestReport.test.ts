import { describe, expect, it } from "vitest";
import type { FullScenarioAnalysis, ScenarioLabSnapshot } from "../../infrastructure/api/testChatApi";
import { buildFullScenarioAnalysisReport, buildScenarioTestReport } from "./scenarioTestReport";

const base: ScenarioLabSnapshot = {
  mode: "SESSION_5_SCENARIO_LAB", badges: ["SYNTHETIC SCENARIO TEST"], scenarios: [],
  activeScenario: { scenario: "C01", name: "FRESH_SWEET_PROSPECT", lifecycle: "RUNNING",
    economicState: "FRESH_PROSPECT", syntheticTelegramId: 9100000001, defects: [], state: {
      buyerStatus: "NONBUYER", buyerStage: "PROSPECT", valueTier: "PROSPECT", purchaseCount: 0,
      lifetimeSpendMinor: 0, ownershipCount: 0, retentionLifecycle: "NOT_A_BUYER",
      timeWasterRisk: "NONE", attentionTier: "MEDIUM", effortMode: "BALANCED",
      commercialMomentum: "COLD", activePurchaseIntent: null, activeSession: null,
    } }, transcript: [], turns: [], latestAnalysis: null, simulatePurchaseEligible: false,
  transport: "TEST_TRANSPORT_NO_WAIT",
  languageCertification: "SYSTEM / BUSINESS CERTIFICATION - LIVE PROVIDER LANGUAGE DEFERRED",
};

describe("buildScenarioTestReport", () => {
  it("exports a prepared scenario before its first turn without inventing diagnostics", () => {
    const report = buildScenarioTestReport(base);
    expect(report).toContain("C01 - FRESH SWEET PROSPECT");
    expect(report).toContain("No conversation yet.");
    expect(report).toContain("No Full Analysis available yet.");
    expect(report).toContain("NOT PROVIDED");
    expect(report).toContain("TEST_TRANSPORT_NO_WAIT");
  });

  it("exports transcript, diagnostics, changes, and the exact canonical analysis", () => {
    const analysis = { finalSalesDecision: { decision: "BUILD_INTEREST", reasonCode: "WARM" },
      customerTemperature: "WARM", commercialReceptiveness: "OPEN",
      inventorySelection: { selectedOfferingId: "offer-1" } };
    const snapshot: ScenarioLabSnapshot = { ...base,
      transcript: [{ role: "user", content: "Hi" }, { role: "assistant", content: "Hey you" },
        { role: "user", content: "What are you hiding?" }, { role: "assistant", content: "Maybe something fun" }],
      turns: [{ turnNumber: 1 }, { turnNumber: 2,
        stateChangesThisTurn: [{ field: "commercialMomentum", before: "COLD", after: "WARM" }],
        systemLogic: { decision: "BUILD_INTEREST", reason: "WARM", offeringSelected: "offer-1" },
        customerValue: { retentionPriority: "LOW", conversationContinuationValue: "HIGH" },
        avaDiagnostics: { persona: { intensity: "MEDIUM", relevantDomains: ["playful"] },
          style: { questionAsked: false, genericFillerRisk: "LOW" }, responseWords: 3, responseChars: 19 },
        temporal: { time: { avaTimezone: "America/New_York", avaDaypart: "evening" }, sleep: "AWAKE" } }],
      latestAnalysis: analysis };
    const report = buildScenarioTestReport(snapshot);
    expect(report).toContain("Turn 1\nCustomer: Hi");
    expect(report).toContain("Turn 2\nCustomer: What are you hiding?");
    expect(report).toContain("commercialMomentum: COLD -> WARM");
    expect(report).toContain("Customer Value / Attention");
    expect(report).toContain("Ava Response Quality Diagnostics");
    expect(report).toContain("Synthetic / Test Commerce");
    expect(report.endsWith(JSON.stringify(analysis, null, 2))).toBe(true);
  });

  it("labels only authoritative certification purchase events as simulated", () => {
    const report = buildScenarioTestReport({ ...base, simulatedProviderPurchase: {
      provenance: "CERTIFICATION_SIMULATED_PROVIDER_EVENT",
      result: { settled: true }, providerTimestamp: "2026-08-28T23:00:00Z",
    } });
    expect(report).toContain("CERTIFICATION_SIMULATED_PROVIDER_EVENT");
    expect(report).toContain("NO REAL FANVUE PURCHASE");
  });

  it("exports scenario, logical-turn, and retry attempt history", () => {
    const snapshot: ScenarioLabSnapshot = { ...base,
      activeScenario: { ...base.activeScenario!, scenarioAttempt: 2 },
      turns: [{ turnNumber: 1, turnAttempt: 2 }],
      transcript: [{ role: "user", content: "Exact inbound" }, { role: "assistant", content: "Repaired reply" }],
      recovery: { retryEligible: true, retryBlocker: null, retryTurn: 1,
        retryCustomerMessage: "Exact inbound", history: {
          scenarioAttempts: [{ scenario_attempt: 1, status: "ABORTED_FOR_REPAIR" }],
          turnAttempts: [{ logical_turn: 1, turn_attempt: 1, status: "SUPERSEDED_BY_RETRY", outbound: "Old reply" },
            { logical_turn: 1, turn_attempt: 2, status: "CURRENT", outbound: "Repaired reply" }],
        } },
    };
    const report = buildScenarioTestReport(snapshot);
    expect(report).toContain("Scenario Attempt:\n2");
    expect(report).toContain("Logical Turn:\n1");
    expect(report).toContain("Turn 1 Attempt 1");
    expect(report).toContain("SUPERSEDED_BY_RETRY");
    expect(report).toContain("ABORTED_FOR_REPAIR");
  });
});

describe("buildFullScenarioAnalysisReport", () => {
  const turn = (logicalTurn: number, evidenceStatus: "MATCHED" | "UNAVAILABLE" = "MATCHED") => ({
    logicalTurn, turnAttempt: logicalTurn === 2 ? 2 : 1, status: "CURRENT" as const,
    attemptId: `attempt-${logicalTurn}`, checkpointId: `checkpoint-${logicalTurn}`,
    persistenceTimestamp: `2026-08-29T12:0${logicalTurn}:00Z`,
    evidenceTimestamp: evidenceStatus === "MATCHED" ? `2026-08-29T12:0${logicalTurn}:00Z` : null,
    evidenceStatus, evidenceUnavailableReason: evidenceStatus === "MATCHED" ? null : "No exact match",
    customer: `Customer ${logicalTurn}`, ava: `Ava ${logicalTurn}`,
    preTurnState: { phase: logicalTurn - 1 }, finalState: { phase: logicalTurn },
    stateChanges: [{ field: "phase", after: logicalTurn }],
    salesBrainFullAnalysis: { finalSalesDecision: { decision: `DECISION_${logicalTurn}` } },
    customerValueAttention: { tier: logicalTurn }, conversationInvestment: { depth: logicalTurn },
    conversationalMemory: { turn: logicalTurn }, memoryDiagnostics: { retrieved: [`fact-${logicalTurn}`] },
    temporalContext: { daypart: "evening" }, sleep: { state: "AWAKE" },
    avaPersonaRuntime: { persona: "AVA" }, styleDiagnostics: { questionAsked: false },
    pacingCalculation: "TEST_TRANSPORT_NO_WAIT", providerDraft: `Draft ${logicalTurn}`,
    rewriteHistory: [], gatewayDiagnostics: { route: "chat" }, commerceAuthority: { allowed: false },
    commerceDiagnostics: { suppression: "NONE" }, purchaseIntent: null, ownership: null,
    session: null, syntheticProvider: { liveProviderCalled: false }, behavior: { inbound: logicalTurn },
    adaptiveCustomer: { behavioral_phase: "QUIET_LOW_RETURN",
      customer_constraints: { engagement: "LOW", buying_intent: false },
      previous_ava_response: logicalTurn > 1 ? `Ava ${logicalTurn - 1}` : "",
      validation_result: { valid: true, structuredTruthUnchanged: true } },
    testTransportResult: "TEST_TRANSPORT_NO_WAIT",
  });
  const payload: FullScenarioAnalysis = {
    mode: "SESSION_5_FULL_SCENARIO_ANALYSIS",
    databaseEnvironment: { databaseName: "creator_os_scenario_lab_test", purpose: "SCENARIO_LAB_OPERATOR" },
    scenario: { scenarioId: "C01", name: "FRESH_SWEET_PROSPECT", scenarioAttempt: 8,
      lifecycle: "RUNNING", economicState: "FRESH_PROSPECT", syntheticTelegramId: 9100000001,
      transport: "TEST_TRANSPORT_NO_WAIT", canonicalTurnCount: 2 },
    currentAccumulatedState: { relationshipState: { phase: "WARM" } },
    turns: [turn(2), turn(1)], finalAccumulatedState: { relationshipState: { phase: "WARM" } },
    attemptAudit: { currentAttempt: { turnAttempts: [{ logical_turn: 2, turn_attempt: 1,
      status: "SUPERSEDED_BY_RETRY" }, { logical_turn: 2, turn_attempt: 2, status: "CURRENT" }] } },
  };

  it("exports every canonical turn chronologically with rich diagnostics", () => {
    const report = buildFullScenarioAnalysisReport(payload);
    expect(report.indexOf("TURN 1")).toBeLessThan(report.indexOf("TURN 2"));
    ["Customer 1", "Ava 1", "DECISION_1", "fact-1", "Customer 2", "Ava 2", "DECISION_2", "fact-2"]
      .forEach((value) => expect(report).toContain(value));
    expect(report).toContain("Current Accumulated State");
    expect(report).toContain("Final Accumulated State");
    expect(report).toContain("QUIET_LOW_RETURN");
    expect(report).toContain('"buying_intent": false');
    expect(report.match(/## TURN 2/g)).toHaveLength(1);
  });

  it("marks unmatched rich evidence unavailable without inventing diagnostics", () => {
    const report = buildFullScenarioAnalysisReport({ ...payload, turns: [turn(1, "UNAVAILABLE")],
      scenario: { ...payload.scenario, canonicalTurnCount: 1 } });
    expect(report).toContain("UNAVAILABLE");
    expect(report).toContain("No exact match");
    expect(report).not.toContain("DECISION_1");
    expect(report).toContain("Customer 1");
    expect(report).toContain("Ava 1");
  });
});
