import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TestChatPage } from "./TestChatPage";
import { getScenarioLab } from "../../infrastructure/api/testChatApi";

const manifest = Array.from({ length: 19 }, (_, index) => ({
  scenario: `C${String(index + 1).padStart(2, "0")}`,
  name: index === 0 ? "FRESH_SWEET_PROSPECT" : `SCENARIO_${index + 1}`,
  description: index === 0 ? "Fresh Sweet Prospect" : `Scenario ${index + 1}`,
  economicStartingState: "FRESH_PROSPECT", syntheticTelegramId: 9100000001 + index, lifecycle: "AVAILABLE",
}));
const empty = { mode: "SESSION_5_SCENARIO_LAB", badges: ["SYNTHETIC SCENARIO TEST", "ISOLATED TEST DATABASE", "NO EXTERNAL SENDS"],
  databaseEnvironment: { databaseName: "creator_os_scenario_lab_test", purpose: "SCENARIO_LAB_OPERATOR" },
  scenarios: manifest, activeScenario: null, transcript: [], turns: [], latestAnalysis: null,
  simulatePurchaseEligible: false, transport: "TEST_TRANSPORT_NO_WAIT",
  languageCertification: "SYSTEM_BUSINESS_ONLY_LIVE_PROVIDER_LANGUAGE_DEFERRED" };
const prepared = { ...empty, activeScenario: { scenario: "C01", name: "FRESH_SWEET_PROSPECT", lifecycle: "RUNNING",
  economicState: "FRESH_PROSPECT", syntheticTelegramId: 9100000001, defects: [], state: {
    buyerStatus: "NONBUYER", buyerStage: "PROSPECT", valueTier: "PROSPECT", purchaseCount: 0,
    lifetimeSpendMinor: 0, ownershipCount: 0, timeWasterRisk: "NONE", attentionTier: "MEDIUM",
    effortMode: "BALANCED", retentionLifecycle: "NOT_A_BUYER", commercialMomentum: "COLD",
    activePurchaseIntent: null, activeSession: null,
  } }, recovery: { retryEligible: false, retryBlocker: "NO VALID PRE_TURN CHECKPOINT",
    retryTurn: null, retryCustomerMessage: null, history: { scenarioAttempts: [], turnAttempts: [] } } };
const turned = { ...prepared, transcript: [{ role: "user", content: "Hey Ava" }, { role: "assistant", content: "I hear you." }],
  turns: [{ turnNumber: 1, stateChangesThisTurn: [{ field: "materialState", after: "NO_MATERIAL_STATE_CHANGE" }] }],
  latestAnalysis: { finalSalesDecision: { decision: "CONTINUE_CONVERSATION", reasonCode: "NO_DIRECT_INTENT" },
    customerValueAttention: { timeWasterRisk: "NONE", effortMode: "BALANCED" } } };
const fullAnalysis = { mode: "SESSION_5_FULL_SCENARIO_ANALYSIS",
  databaseEnvironment: { databaseName: "creator_os_scenario_lab_test", purpose: "SCENARIO_LAB_OPERATOR" },
  scenario: { scenarioId: "C01", name: "FRESH_SWEET_PROSPECT", scenarioAttempt: 8,
    lifecycle: "RUNNING", economicState: "FRESH_PROSPECT", syntheticTelegramId: 9100000001,
    transport: "TEST_TRANSPORT_NO_WAIT", canonicalTurnCount: 1 },
  currentAccumulatedState: { buyerStatus: "NONBUYER" },
  turns: [{ logicalTurn: 1, turnAttempt: 1, status: "CURRENT", attemptId: "attempt-1",
    checkpointId: "checkpoint-1", persistenceTimestamp: "2026-08-29T12:00:00Z",
    evidenceTimestamp: "2026-08-29T12:00:00Z", evidenceStatus: "MATCHED",
    evidenceUnavailableReason: null, customer: "Hey Ava", ava: "I hear you.", preTurnState: {},
    finalState: {}, stateChanges: [], salesBrainFullAnalysis: { finalSalesDecision: { decision: "CONTINUE" } },
    customerValueAttention: {}, conversationInvestment: {}, conversationalMemory: {}, memoryDiagnostics: {},
    temporalContext: {}, sleep: {}, avaPersonaRuntime: {}, styleDiagnostics: {}, pacingCalculation: "TEST_TRANSPORT_NO_WAIT",
    providerDraft: "I hear you.", rewriteHistory: [], gatewayDiagnostics: {}, commerceAuthority: {},
    commerceDiagnostics: {}, purchaseIntent: null, ownership: null, session: null, syntheticProvider: {},
    behavior: {}, testTransportResult: "TEST_TRANSPORT_NO_WAIT" }],
  finalAccumulatedState: { buyerStatus: "NONBUYER" }, attemptAudit: {} };

describe("TestChatPage Session 5 scenario lab", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("maps scenario authorization and purpose failures to safe operator detail", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "secret internal detail" }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        detail: "Session 5 database purpose mismatch: expected SCENARIO_LAB_OPERATOR",
      }), { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getScenarioLab()).rejects.toThrow("Developer authorization failed.");
    await expect(getScenarioLab()).rejects.toThrow("Database purpose mismatch.");
  });

  it("recovers initial scenario loading after a transient API reload outage", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(JSON.stringify(prepared), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Scenario API unavailable.");
    await waitFor(() => expect(screen.getByText(/C01 — FRESH SWEET PROSPECT/)).toBeInTheDocument(), {
      timeout: 2500,
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("loads, prepares C01, sends, and copies full analysis", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(empty), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: prepared }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: turned }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(fullAnalysis), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock); render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("SYNTHETIC SCENARIO TEST");
    expect(screen.getByText("Scenario Lab DB: creator_os_scenario_lab_test · Purpose: SCENARIO_LAB_OPERATOR")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "C01 — Fresh Sweet Prospect" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Prepare Scenario" }));
    expect(await screen.findByText(/C01 — FRESH SWEET PROSPECT/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Hey Ava" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findAllByText("I hear you.")).toHaveLength(2);
    expect(screen.getByText("REAL PROVIDER IS OPTIONAL · EXTERNAL DELIVERY REMAINS DISABLED")).toBeInTheDocument();
    expect(screen.getByLabelText("Language")).toHaveValue("REAL_AVA_LANGUAGE");
    expect(fetchMock).toHaveBeenNthCalledWith(3, expect.stringContaining("/scenarios/turn"),
      expect.objectContaining({ body: JSON.stringify({
        customer_message: "Hey Ava", language_mode: "REAL_AVA_LANGUAGE",
      }) }));
    fireEvent.click(screen.getByRole("button", { name: "Copy Full Scenario Analysis" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("finalSalesDecision")));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/sessions"))).toBe(false);
  });

  it("copies the selected completed C02 attempt and reports visible success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const completedC02 = { ...prepared, activeScenario: { ...prepared.activeScenario!, scenario: "C02",
      name: "FRESH_QUIET_PROSPECT", lifecycle: "COMPLETED", grade: "FAIL", syntheticTelegramId: 9100000002 } };
    const c02Analysis = { ...fullAnalysis, scenario: { ...fullAnalysis.scenario, scenarioId: "C02",
      name: "FRESH_QUIET_PROSPECT", scenarioAttempt: 3, lifecycle: "COMPLETED",
      syntheticTelegramId: 9100000002, canonicalTurnCount: 7 }, turns: [{ ...fullAnalysis.turns[0],
        customer: "just scrolling around killing time", ava: "Scrolling can get dull fast." }] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(completedC02), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(c02Analysis), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText(/C02.*FRESH QUIET PROSPECT/);
    fireEvent.click(screen.getByRole("button", { name: "Copy Full Scenario Analysis" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("just scrolling around killing time")));
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining("scenario_id=C02"), expect.anything());
    expect(await screen.findByText("Full Scenario Analysis copied — C02 Attempt 3")).toBeInTheDocument();
  });

  it("shows the complete report fallback when clipboard writing fails", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(prepared), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(fullAnalysis), { status: 200 })));
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText(/C01.*FRESH SWEET PROSPECT/);
    fireEvent.click(screen.getByRole("button", { name: "Copy Full Scenario Analysis" }));
    const report = await screen.findByLabelText("Full Scenario Analysis report");
    expect((report as HTMLTextAreaElement).value).toContain("# FULL SCENARIO ANALYSIS");
    expect(screen.getByText(/Clipboard write failed.*C01 Attempt 8/)).toBeInTheDocument();
  });

  it("surfaces a scenario-analysis API failure", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn() } });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(prepared), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "C02 analysis unavailable" }), { status: 409 })));
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText(/C01.*FRESH SWEET PROSPECT/);
    fireEvent.click(screen.getByRole("button", { name: "Copy Full Scenario Analysis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("C02 analysis unavailable");
    expect(screen.getByText("Copy failed")).toBeInTheDocument();
  });

  it("gates simulation and lifecycle controls", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(prepared), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...fullAnalysis, turns: [], scenario: {
        ...fullAnalysis.scenario, canonicalTurnCount: 0,
      } }), { status: 200 })));
    render(<MemoryRouter><TestChatPage /></MemoryRouter>); await screen.findByText(/C01 — FRESH SWEET PROSPECT/);
    expect(screen.queryByRole("button", { name: "Copy Test Report" })).not.toBeInTheDocument();
    const analysisButton = screen.getByRole("button", { name: "Copy Full Scenario Analysis" });
    fireEvent.click(analysisButton);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("canonicalTurnCount")));
    expect(await screen.findByRole("button", { name: "Copied!" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Simulate Provider Purchase" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retry Previous Turn" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Restart Entire Scenario" })).toBeEnabled();
    const retry = screen.getByRole("button", { name: "Retry Previous Turn" });
    const restart = screen.getByRole("button", { name: "Restart Entire Scenario" });
    const copy = screen.getByRole("button", { name: /Copy Full Scenario Analysis|Copied!/ });
    const toolbar = retry.closest(".test-chat-live-toolbar");
    expect(toolbar).toContainElement(restart);
    expect(toolbar).toContainElement(copy);
    expect(retry.compareDocumentPosition(restart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(restart.compareDocumentPosition(copy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Retry Previous Turn" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Restart Entire Scenario" })).toHaveLength(1);
    const lowerActions = screen.getByRole("button", { name: "Simulate Provider Purchase" }).closest(".test-chat-actions");
    expect(lowerActions).not.toContainElement(retry);
    expect(lowerActions).not.toContainElement(restart);
    expect(lowerActions).toContainElement(screen.getByRole("button", { name: "Complete PASS" }));
    expect(lowerActions).toContainElement(screen.getByRole("button", { name: "Finish Current Scenario" }));
    expect(screen.getByText("NO VALID PRE_TURN CHECKPOINT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish Current Scenario" })).toBeDisabled();
    expect(screen.getByLabelText("Customer Scenario")).toBeDisabled();
    expect(screen.getByText(/Scenario selector locked while C01 is running/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear Chat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reset Memory" })).not.toBeInTheDocument();
  });

  it("renders the canonical matrix and selecting is inert until Prepare Scenario", async () => {
    const c19 = { ...prepared, activeScenario: { ...prepared.activeScenario!, scenario: "C19",
      name: "ACTIVE_SESSION_BUYER", syntheticTelegramId: 9100000019,
      economicState: "ACTIVE_SESSION_BUYER" } };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(empty), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: c19 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("SYNTHETIC SCENARIO TEST");
    expect(screen.getAllByRole("option")).toHaveLength(21);
    const scenarioOptions = screen.getAllByRole("option").slice(0, manifest.length);
    for (const [index, item] of manifest.entries()) {
      expect(scenarioOptions[index]).toHaveValue(item.scenario);
      expect(scenarioOptions[index]).toHaveTextContent(item.description);
    }
    fireEvent.change(screen.getByLabelText("Customer Scenario"), { target: { value: "C19" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Language")).toHaveValue("REAL_AVA_LANGUAGE");
    fireEvent.click(screen.getByRole("button", { name: "Prepare Scenario" }));
    await screen.findByRole("heading", { name: /C19.*ACTIVE SESSION BUYER/ });
    expect(String(fetchMock.mock.calls[1]![1]?.body)).toContain('"scenario_id":"C19"');
    expect(screen.getByLabelText("Language")).toHaveValue("REAL_AVA_LANGUAGE");
  });

  it("finishes a completed scenario through snapshot reset and clean verification", async () => {
    const completed = { ...prepared, activeScenario: { ...prepared.activeScenario!, lifecycle: "COMPLETED", grade: "PASS" } };
    const snapshotted = { ...completed, activeScenario: { ...completed.activeScenario!, lifecycle: "SNAPSHOTTED" } };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(completed), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: snapshotted }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: empty }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ scenario: "C01", result: "VERIFIED_CLEAN" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    const finish = await screen.findByRole("button", { name: "Finish Current Scenario" });
    expect(finish).toBeEnabled();
    fireEvent.click(finish);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(String(fetchMock.mock.calls[1]![0])).toContain("/scenarios/snapshot");
    expect(String(fetchMock.mock.calls[1]![1]?.body)).toContain('"scenario_id":"C01"');
    expect(String(fetchMock.mock.calls[2]![0])).toContain("/scenarios/reset");
    expect(String(fetchMock.mock.calls[2]![1]?.body)).toContain('"scenario_id":"C01"');
    expect(String(fetchMock.mock.calls[3]![0])).toContain("/scenarios/verify-clean");
    expect(await screen.findByLabelText("Customer Scenario")).toBeEnabled();
    expect(screen.getByLabelText("Language")).toHaveValue("REAL_AVA_LANGUAGE");
  });

  it("retries the exact stored turn through one API action without Send", async () => {
    const retryReady = { ...turned, recovery: { ...prepared.recovery, retryEligible: true,
      retryBlocker: null, retryTurn: 2,
      retryCustomerMessage: "Yeah work was kinda brutal today lol. Just glad to finally be home." } };
    const retried = { ...retryReady,
      turns: [...turned.turns, { turnNumber: 2, turnAttempt: 2, stateChangesThisTurn: [] }],
      transcript: [...turned.transcript,
        { role: "user", content: "Yeah work was kinda brutal today lol. Just glad to finally be home." },
        { role: "assistant", content: "ugh, at least you're finally home now" }] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(retryReady), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: retried }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("repair retest");
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText(/C01 — FRESH SWEET PROSPECT/);
    fireEvent.click(screen.getByRole("button", { name: "Retry Previous Turn" }));
    expect(await screen.findByText("TURN 2 RETRIED — ATTEMPT 2")).toBeInTheDocument();
    expect(screen.getAllByText("ugh, at least you're finally home now")).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]![0])).toContain("/retry-previous-turn");
    expect(String(fetchMock.mock.calls[1]![1]?.body)).not.toContain("customer_message");
    expect(String(fetchMock.mock.calls[1]![1]?.body)).toContain("recovery_operation_id");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/turn"))).toBe(false);
  });

  it("locks Send Retry and Restart immediately during a slow retry and ignores a rapid double click", async () => {
    const retryReady = { ...turned, recovery: { ...prepared.recovery, retryEligible: true,
      retryBlocker: null, retryTurn: 2, retryCustomerMessage: "Exact retry input" } };
    let resolveRetry!: (value: Response) => void;
    const retryResponse = new Promise<Response>((resolve) => { resolveRetry = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(retryReady), { status: 200 }))
      .mockImplementationOnce(() => retryResponse);
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("repair retest");
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByRole("button", { name: "Retry Previous Turn" });
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "stale composer input" } });
    const retry = screen.getByRole("button", { name: "Retry Previous Turn" });
    fireEvent.click(retry); fireEvent.click(retry);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: /RETRYING TURN 2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Restart Entire Scenario" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Sending/ })).toBeDisabled();
    expect(screen.getByLabelText("Customer")).toHaveValue("");
    resolveRetry(new Response(JSON.stringify({ snapshot: retryReady }), { status: 200 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry Previous Turn" })).toBeEnabled());
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/turn"))).toBe(false);
  });

  it("Restart is a non-submit action and does not invoke the ordinary turn endpoint", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(prepared), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot: prepared }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("restart test");
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByRole("button", { name: "Restart Entire Scenario" });
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "must not send" } });
    fireEvent.click(screen.getByRole("button", { name: "Restart Entire Scenario" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]![0])).toContain("/restart");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/turn"))).toBe(false);
  });

  it("preserves the Live Controlled Test observer", async () => {
    const live = { mode: "LIVE_CONTROLLED_TEST", badges: [], configured: true, readOnly: true, pollIntervalSeconds: 3,
      customer: {}, conversation: [{ role: "assistant", content: "Persisted Ava reply", providerMessageId: 5341 }],
      turns: [], currentState: {}, memory: {}, timeContext: {}, pacing: {}, ordinaryReplyOperations: [],
      identityDiagnostics: {}, commerceState: {}, recommendationDecision: {}, fingerprintDiagnostics: {},
      sessionDiagnostics: {}, purchaseAcknowledgement: {}, controlledTestOffering: {}, runtimeSafety: {},
      resetDryRun: { allowed: false, executed: false, blockers: [], wouldClear: {}, wouldPreserve: [] } };
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(empty), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(live), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock); render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("SYNTHETIC SCENARIO TEST"); fireEvent.click(screen.getByRole("button", { name: "Live Controlled Test" }));
    expect(await screen.findByText("LIVE CONTROLLED TEST")).toBeInTheDocument();
    expect(screen.getByText("Persisted Ava reply")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes("/live") && init?.method === "POST")).toBe(false);
  });
});
