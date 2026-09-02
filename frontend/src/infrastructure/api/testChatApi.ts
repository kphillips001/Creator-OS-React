import type { TestChatSession, TestChatTurn } from "../../features/test-chat/types";
import { environment } from "../config/environment";
import { developerFetch } from "./developerFetch";

export type TestChatErrorDetails = {
  exception_type: string; exception_message: string; file: string;
  line_number: string; stack_trace: string; root_cause: string;
};

export class TestChatApiError extends Error {
  constructor(public readonly details: TestChatErrorDetails) {
    super(details.exception_message);
  }
}

type ApiSession = {
  session_id: string;
  test_user: { name: string; relationship: string; buyer_tier: string };
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  reply?: string;
  decision?: {
    intent: string; relationship: string; sell: boolean;
    provider_selected: string | null; reason: string;
    product: string | null; asset: string | null;
    commerce_lookup_attempted: boolean; requested_media_type: string | null;
    requested_themes: string[]; offering_selected: boolean;
    offering_id: string | null; offering_type: string | null;
    offering_title: string | null; price_minor: number | null;
    currency: string | null; primary_sales_channel: string;
    provider: string | null; fulfillable: boolean;
    recommendation_reason: string | null; no_offering_reason: string | null;
    delivery_url: string | null;
    legacy_offer_requested?: boolean; commerce_offer_authorized?: boolean;
    final_offer_authorized?: boolean; commerce_execution_policy?: string | null;
    customer_sales_decision?: string | null;
    customer_sales_reason_code?: string | null;
    authoritative_offering_selected?: boolean; selection_source?: string | null;
    commerce_prompt_mode?: string | null; legacy_recommendation_used?: boolean;
  };
  external_sends_disabled: boolean;
};

const mapSession = (body: ApiSession): TestChatSession => ({
  sessionId: body.session_id,
  testUser: {
    name: body.test_user.name,
    relationship: body.test_user.relationship,
    buyerTier: body.test_user.buyer_tier,
  },
  messages: body.messages,
  reply: body.reply,
  decision: body.decision,
  externalSendsDisabled: body.external_sends_disabled,
});

async function post(path: string, body?: object): Promise<TestChatSession> {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat${path}`, {
    method: "POST",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({})) as ApiSession & { detail?: string };
  if (!response.ok || !payload.session_id) throw new Error(payload.detail || "Test Chat request failed.");
  return mapSession(payload);
}

export const newTestChat = () => post("/sessions");
export async function sendTestChatMessage(sessionId: string, customerMessage: string): Promise<TestChatTurn> {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/turns`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, customer_message: customerMessage }),
  });
  const body = await response.json().catch(() => ({})) as TestChatTurn & { detail?: string | TestChatErrorDetails };
  if (!response.ok) {
    if (body.detail && typeof body.detail === "object") throw new TestChatApiError(body.detail);
    throw new Error(body.detail || "Test Chat request failed.");
  }
  if (typeof body.reply !== "string") throw new Error("Test Chat request failed.");
  return body;
}
export const clearTestChat = (sessionId: string) => post("/clear", { session_id: sessionId });
export const resetTestChatMemory = (sessionId: string) =>
  post("/reset-memory", { session_id: sessionId });

export type LiveControlledSnapshot = {
  mode: "LIVE_CONTROLLED_TEST"; badges: string[]; configured: boolean; readOnly: boolean;
  customer: Record<string, unknown>;
  conversation: Array<{ role: "user" | "assistant"; content: string; timestamp?: string | null;
    providerMessageId?: number | null; classification?: string; replyOperationState?: string }>;
  turns: Array<{ turn: number; customerMessage: string; reply?: string; inboundProviderMessageId?: number;
    decision: Record<string, unknown> }>;
  currentState: Record<string, unknown>; memory: Record<string, unknown>;
  timeContext: Record<string, unknown>; pacing: Record<string, unknown>;
  sleep?: Record<string, unknown>;
  ordinaryReplyOperations: Array<Record<string, unknown>>;
  identityDiagnostics: Record<string, unknown>;
  commerceState: Record<string, unknown>;
  recommendationDecision: Record<string, unknown>;
  fingerprintDiagnostics: Record<string, unknown>;
  sessionDiagnostics: Record<string, unknown>;
  purchaseAcknowledgement: Record<string, unknown>;
  controlledTestOffering: Record<string, unknown>;
  runtimeSafety: Record<string, unknown>;
  resetDryRun: { allowed: boolean; executed: boolean; blockers: string[];
    wouldClear: Record<string, number>; wouldPreserve: string[] };
  pollIntervalSeconds: number;
};

async function getLive(path = ""): Promise<LiveControlledSnapshot> {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/live${path}`);
  const body = await response.json().catch(() => ({})) as LiveControlledSnapshot & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "No controlled Telegram test customer configured");
  return body;
}

export const getLiveControlledTest = () => getLive();
export const getControlledResetDryRun = async () => {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/live/reset-dry-run`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body as { detail?: string }).detail || "Reset safety check failed");
  return body as LiveControlledSnapshot["resetDryRun"];
};
export const executeControlledReset = async () => {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/live/reset`, { method: "POST" });
  const body = await response.json().catch(() => ({})) as { executed?: boolean };
  if (!response.ok || !body.executed) throw new Error("Controlled reset was blocked by a safety precondition");
  return body;
};

export type ScenarioLabSnapshot = {
  mode: "SESSION_5_SCENARIO_LAB";
  badges: string[];
  databaseEnvironment?: { databaseName: string; purpose: string };
  scenarios: Array<{ scenario: string; name: string; description: string;
    economicStartingState: string; syntheticTelegramId: number; lifecycle: string }>;
  activeScenario: null | { scenario: string; name: string; lifecycle: string;
    economicState: string; syntheticTelegramId: number; state: Record<string, unknown>;
    defects: Array<Record<string, unknown>>; grade?: string | null; scenarioAttempt?: number };
  transcript: Array<{ role: "user" | "assistant"; content: string }>;
  turns: Array<Record<string, unknown>>;
  latestAnalysis: Record<string, unknown> | null;
  simulatePurchaseEligible: boolean;
  simulatedProviderPurchase?: null | { provenance: string; result: Record<string, unknown> | null;
    providerTimestamp: string };
  transport: "TEST_TRANSPORT_NO_WAIT";
  languageCertification: string;
  languageModes?: Array<"REAL_AVA_LANGUAGE" | "DETERMINISTIC_CERTIFICATION">;
  defaultLanguageMode?: "REAL_AVA_LANGUAGE" | "DETERMINISTIC_CERTIFICATION";
  recovery?: { retryEligible: boolean; retryBlocker: string | null; retryTurn: number | null;
    retryCustomerMessage: string | null; history: { scenarioAttempts: Array<Record<string, unknown>>;
      turnAttempts: Array<Record<string, unknown>> };
    historicalScenarioAttempts?: { scenarioAttempts: Array<Record<string, unknown>>;
      turnAttempts: Array<Record<string, unknown>> } };
};

export type FullScenarioAnalysis = {
  mode: "SESSION_5_FULL_SCENARIO_ANALYSIS";
  databaseEnvironment: { databaseName: string; purpose: string };
  scenario: { scenarioId: string; name: string; scenarioAttempt: number;
    lifecycle: string; economicState: string; syntheticTelegramId: number;
    transport: string; canonicalTurnCount: number };
  currentAccumulatedState: Record<string, unknown>;
  turns: Array<{ logicalTurn: number; turnAttempt: number; status: "CURRENT";
    attemptId: string; checkpointId: string; persistenceTimestamp: string;
    evidenceTimestamp: string | null; evidenceStatus: "MATCHED" | "UNAVAILABLE" | "AMBIGUOUS";
    evidenceUnavailableReason: string | null; customer: string; ava: string;
    preTurnState: unknown; finalState: unknown; stateChanges: unknown;
    salesBrainFullAnalysis: unknown; customerValueAttention: unknown;
    conversationInvestment: unknown; conversationalMemory: unknown;
    memoryDiagnostics: unknown; temporalContext: unknown; sleep: unknown;
    avaPersonaRuntime: unknown; styleDiagnostics: unknown; pacingCalculation: unknown;
    providerDraft: unknown; rewriteHistory: unknown; gatewayDiagnostics: unknown;
    commerceAuthority: unknown; commerceDiagnostics: unknown; purchaseIntent: unknown;
    ownership: unknown; session: unknown; syntheticProvider: unknown;
    behavior: unknown; adaptiveCustomer?: unknown; syntheticPpvPresentation?: unknown;
    testTransportResult: unknown }>;
  finalAccumulatedState: Record<string, unknown>;
  attemptAudit: Record<string, unknown>;
};

async function scenarioRequest(path = "", body?: object, method = "GET"): Promise<ScenarioLabSnapshot> {
  let response: Response;
  try {
    response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/scenarios${path}`, {
      method, headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Scenario API unavailable.");
  }
  const payload = await response.json().catch(() => ({})) as ScenarioLabSnapshot & {
    detail?: unknown; snapshot?: ScenarioLabSnapshot;
  };
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "";
    if (response.status === 401 || response.status === 403) {
      throw new Error("Developer authorization failed.");
    }
    if (response.status === 503) {
      throw new Error(detail.toLowerCase().includes("purpose mismatch")
        ? "Database purpose mismatch."
        : "Operator database unavailable.");
    }
    if (response.status >= 500) throw new Error("Scenario API unavailable.");
    throw new Error(detail || `Scenario request failed (HTTP ${response.status}).`);
  }
  return payload.snapshot || payload;
}

export const getScenarioLab = () => scenarioRequest();
export async function getFullScenarioAnalysis(scenarioId: string): Promise<FullScenarioAnalysis> {
  let response: Response;
  try {
    response = await developerFetch(
      `${environment.apiBaseUrl}/developer/test-chat/scenarios/full-analysis?scenario_id=${encodeURIComponent(scenarioId)}`,
    );
  } catch {
    throw new Error("Scenario analysis API unavailable.");
  }
  const body = await response.json().catch(() => ({})) as FullScenarioAnalysis & { detail?: string };
  if (!response.ok) throw new Error(body.detail || `Scenario analysis request failed (HTTP ${response.status}).`);
  return body;
}
export const prepareScenario = (scenarioId: string) =>
  scenarioRequest("/prepare", { scenario_id: scenarioId }, "POST");
export type ScenarioLanguageMode = "REAL_AVA_LANGUAGE" | "DETERMINISTIC_CERTIFICATION";
export const sendScenarioTurn = (customerMessage: string, languageMode: ScenarioLanguageMode) =>
  scenarioRequest("/turn", { customer_message: customerMessage, language_mode: languageMode }, "POST");
export const simulateScenarioPurchase = () => scenarioRequest("/simulate-purchase", undefined, "POST");
export const retryPreviousScenarioTurn = (reason?: string, recoveryOperationId?: string) =>
  scenarioRequest("/retry-previous-turn", {
    reason: reason || null,
    recovery_operation_id: recoveryOperationId || crypto.randomUUID(),
  }, "POST");
export const restartEntireScenario = (scenarioId: string, reason?: string) =>
  scenarioRequest("/restart", { scenario_id: scenarioId, reason: reason || null }, "POST");
export const addScenarioDefect = (severity: string, note: string) =>
  scenarioRequest("/defect", { severity, note }, "POST");
export const completeScenario = (grade: string) =>
  scenarioRequest("/complete", { grade }, "POST");
export const snapshotScenario = (scenarioId: string) =>
  scenarioRequest("/snapshot", { scenario_id: scenarioId }, "POST");
export const resetScenario = (scenarioId: string) =>
  scenarioRequest("/reset", { scenario_id: scenarioId }, "POST");
export async function verifyScenarioClean(): Promise<Record<string, unknown>> {
  const response = await developerFetch(`${environment.apiBaseUrl}/developer/test-chat/scenarios/verify-clean`);
  const body = await response.json().catch(() => ({})) as Record<string, unknown> & { detail?: string };
  if (!response.ok) throw new Error(String(body.detail || "Scenario reset verification failed."));
  return body;
}
