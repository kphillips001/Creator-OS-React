import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  clearTestChat,
  newTestChat,
  resetTestChatMemory,
  sendTestChatMessage,
  TestChatApiError,
  type TestChatErrorDetails,
  getLiveControlledTest,
  type LiveControlledSnapshot,
  executeControlledReset,
  getControlledResetDryRun,
  addScenarioDefect, completeScenario, getScenarioLab, prepareScenario,
  getFullScenarioAnalysis,
  resetScenario, sendScenarioTurn, simulateScenarioPurchase, snapshotScenario,
  restartEntireScenario, retryPreviousScenarioTurn,
  verifyScenarioClean, type ScenarioLabSnapshot,
} from "../../infrastructure/api/testChatApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CommerceLearningProfile,
  RecommendationDiagnostics,
  TestChatSession,
} from "./types";
import { buildFullAnalysis } from "./fullAnalysisExport";
import { buildFullScenarioAnalysisReport } from "./scenarioTestReport";
import "./test-chat.css";

const label = (value: string | null | undefined) => value || "None";

export function TestChatPage() {
  const [mode, setMode] = useState<"synthetic" | "live">("synthetic");
  const [live, setLive] = useState<LiveControlledSnapshot | null>(null);
  type LegacySession = TestChatSession & { decision: NonNullable<TestChatSession["decision"]> & { delivery_url: string } };
  const [session, setSession] = useState<LegacySession>({} as LegacySession);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorDetails, setErrorDetails] = useState<TestChatErrorDetails>({} as TestChatErrorDetails);

  const run = async (action: () => Promise<TestChatSession>) => {
    setBusy(true);
    setError("");
    setErrorDetails({} as TestChatErrorDetails);
    try { setSession(await action() as LegacySession); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Test Chat request failed."); }
    finally { setBusy(false); }
  };

  useEffect(() => { /* Legacy synthetic sessions are intentionally not auto-created. */ }, []);
  useEffect(() => {
    if (mode !== "live") return;
    let active = true;
    const refresh = () => void getLiveControlledTest().then((value) => {
      if (active) { setLive(value); setError(""); }
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Live observer unavailable"); });
    refresh(); const timer = window.setInterval(refresh, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [mode]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!session || !value || busy) return;
    setMessage(""); setBusy(true); setError(""); setErrorDetails({} as TestChatErrorDetails);
    void sendTestChatMessage(session.sessionId, value).then((turn) => setSession((current) => ({
      ...current,
      messages: [...current.messages, { role: "user", content: value }, { role: "assistant", content: turn.reply }],
      reply: turn.reply,
      decision: { ...turn },
    } as LegacySession))).catch((reason) => {
      if (reason instanceof TestChatApiError) setErrorDetails(reason.details);
      else setError(reason instanceof Error ? reason.message : "Test Chat request failed.");
    }).finally(() => setBusy(false));
  };

  return <section className="test-chat-page">
    <PageHeader title="Test Chat" description={mode === "synthetic" ? "Exercise the Sales Agent brain with a synthetic customer." : "Observe the persisted production decision path for the controlled Telegram test customer."} />
    <div className="test-chat-mode" role="group" aria-label="Test Chat mode">
      <button className={mode === "synthetic" ? "is-active" : ""} onClick={() => setMode("synthetic")} type="button">Synthetic Test</button>
      <button className={mode === "live" ? "is-active" : ""} onClick={() => setMode("live")} type="button">Live Controlled Test</button>
    </div>
    {mode === "live" && <LiveControlledTest snapshot={live} error={error} />}
    {mode === "synthetic" && <SyntheticScenarioLab />}
    {mode === "synthetic" && false && <>
    <div className="test-chat-actions">
      <button disabled={busy} onClick={() => void run(newTestChat)} type="button">New Chat</button>
      <button disabled={busy || !session} onClick={() => session && void run(() => clearTestChat(session.sessionId))} type="button">Clear Chat</button>
      <button disabled={busy || !session} onClick={() => session && void run(() => resetTestChatMemory(session.sessionId))} type="button">Reset Memory</button>
    </div>
    {error && <div className="test-chat-error" role="alert">{error}</div>}
    {errorDetails && <section className="test-chat-card test-chat-error-card" role="alert"><h2>Sales Agent Error</h2><dl><div><dt>Exception type</dt><dd>{errorDetails.exception_type}</dd></div><div><dt>Exception message</dt><dd>{errorDetails.exception_message}</dd></div><div><dt>File</dt><dd>{errorDetails.file}</dd></div><div><dt>Line number</dt><dd>{errorDetails.line_number}</dd></div><div><dt>Root cause</dt><dd>{errorDetails.root_cause}</dd></div></dl><details><summary>Stack trace</summary><pre>{errorDetails.stack_trace}</pre></details></section>}
    {session && <>
      <section className="test-chat-card test-chat-user" aria-labelledby="test-user-heading">
        <h2 id="test-user-heading">Test User</h2>
        <dl><div><dt>Relationship</dt><dd>{session.testUser.relationship}</dd></div><div><dt>Buyer Tier</dt><dd>{session.testUser.buyerTier}</dd></div></dl>
      </section>
      <section className="test-chat-card" aria-labelledby="conversation-heading">
        <h2 id="conversation-heading">Conversation</h2>
        <div className="test-chat-transcript">
          {session.messages.length === 0 && <p className="test-chat-empty">No messages yet.</p>}
          {session.messages.map((item, index) => <p className={`test-chat-message test-chat-message--${item.role}`} key={`${item.role}-${index}`}><strong>{item.role === "user" ? "Customer" : "AI"}:</strong> {item.content}</p>)}
        </div>
        <form className="test-chat-form" onSubmit={submit}><label htmlFor="test-chat-message">Customer</label><div><input id="test-chat-message" maxLength={4000} onChange={(event) => setMessage(event.target.value)} placeholder="Type a customer message" value={message} /><button disabled={busy || !message.trim()} type="submit">{busy ? "Sending…" : "Send"}</button></div></form>
      </section>
      <section className="test-chat-card" aria-labelledby="response-heading"><h2 id="response-heading">AI Response</h2><p>{session.reply || "No response yet."}</p></section>
      <section className="test-chat-card" aria-labelledby="decision-heading"><h2 id="decision-heading">Decision Summary</h2>
        <dl className="test-chat-decision"><div><dt>Intent</dt><dd>{label(session.decision?.intent)}</dd></div><div><dt>Relationship</dt><dd>{label(session.decision?.relationship)}</dd></div><div><dt>Sell</dt><dd>{session.decision ? (session.decision.sell ? "YES" : "NO") : "None"}</dd></div><div><dt>Sales Brain decision</dt><dd>{label(session.decision?.customer_sales_decision)}</dd></div><div><dt>Sales Brain reason</dt><dd>{label(session.decision?.customer_sales_reason_code)}</dd></div><div><dt>Commerce policy</dt><dd>{label(session.decision?.commerce_execution_policy)}</dd></div><div><dt>Commerce prompt mode</dt><dd>{label(session.decision?.commerce_prompt_mode)}</dd></div><div><dt>Commerce mode</dt><dd>{label(session.decision?.commerce_mode)}</dd></div><div><dt>Compatibility mode</dt><dd>{session.decision ? (session.decision.compatibility_mode ? "Yes" : "No") : "None"}</dd></div><div><dt>Selection source</dt><dd>{label(session.decision?.selection_source)}</dd></div><div><dt>Delivery source</dt><dd>{label(session.decision?.delivery_source)}</dd></div><div><dt>Memory source</dt><dd>{label(session.decision?.memory_source)}</dd></div><div><dt>Eligibility source</dt><dd>{label(session.decision?.eligibility_source)}</dd></div><div><dt>Recommendation source</dt><dd>{label(session.decision?.recommendation_source)}</dd></div><div><dt>Legacy memory mutated</dt><dd>{session.decision ? (session.decision.legacy_memory_mutated ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy delivery used</dt><dd>{session.decision ? (session.decision.legacy_delivery_used ? "Yes" : "No") : "None"}</dd></div><div><dt>Authoritative offering selected</dt><dd>{session.decision ? (session.decision.authoritative_offering_selected ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy recommendation used</dt><dd>{session.decision ? (session.decision.legacy_recommendation_used ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy offer requested</dt><dd>{session.decision ? (session.decision.legacy_offer_requested ? "Yes" : "No") : "None"}</dd></div><div><dt>Commerce authorized</dt><dd>{session.decision ? (session.decision.commerce_offer_authorized ? "Yes" : "No") : "None"}</dd></div><div><dt>Final authorization</dt><dd>{session.decision ? (session.decision.final_offer_authorized ? "Yes" : "No") : "None"}</dd></div><div><dt>AI Provider</dt><dd>{label(session.decision?.provider_selected)}</dd></div><div><dt>Reason</dt><dd>{label(session.decision?.reason)}</dd></div><div><dt>Commerce lookup attempted</dt><dd>{session.decision ? (session.decision.commerce_lookup_attempted ? "Yes" : "No") : "None"}</dd></div><div><dt>Requested media type</dt><dd>{label(session.decision?.requested_media_type)}</dd></div><div><dt>Requested themes</dt><dd>{session.decision?.requested_themes?.length ? session.decision.requested_themes.join(", ") : "None"}</dd></div><div><dt>Offering selected</dt><dd>{session.decision ? (session.decision.offering_selected ? "Yes" : "No") : "None"}</dd></div><div><dt>Offering ID</dt><dd>{label(session.decision?.offering_id)}</dd></div><div><dt>Offering type</dt><dd>{label(session.decision?.offering_type)}</dd></div><div><dt>Title</dt><dd>{label(session.decision?.offering_title)}</dd></div><div><dt>Price</dt><dd>{session.decision?.price_minor != null ? new Intl.NumberFormat(undefined, { style: "currency", currency: session.decision.currency || "USD" }).format(session.decision.price_minor! / 100) : "None"}</dd></div><div><dt>Primary Sales Channel</dt><dd>{label(session.decision?.primary_sales_channel)}</dd></div><div><dt>Provider</dt><dd>{label(session.decision?.provider)}</dd></div><div><dt>Fulfillable</dt><dd>{session.decision ? (session.decision.fulfillable ? "Yes" : "No") : "None"}</dd></div><div><dt>Recommendation reason</dt><dd>{label(session.decision?.recommendation_reason)}</dd></div><div><dt>No-offering reason</dt><dd>{label(session.decision?.no_offering_reason)}</dd></div><div><dt>Delivery URL</dt><dd>{session.decision?.delivery_url ? <a href={session.decision.delivery_url} rel="noreferrer" target="_blank">{session.decision.delivery_url}</a> : "None"}</dd></div><div><dt>Legacy Product</dt><dd>{label(session.decision?.product)}</dd></div><div><dt>Legacy Asset</dt><dd>{label(session.decision?.asset)}</dd></div></dl>
      </section>
      <RecommendationDecision
        diagnostics={session.decision?.recommendation_diagnostics}
        learning={session.decision?.commerce_learning_profile}
        sell={session.decision?.sell}
        salesReason={session.decision?.customer_sales_reason_code ?? undefined}
      />
      <div className="test-chat-safety" role="status">🚫 External Sends Disabled</div>
    </>}
    </>}
  </section>;
}

function SyntheticScenarioLab() {
  const [snapshot, setSnapshot] = useState<ScenarioLabSnapshot | null>(null);
  const [selected, setSelected] = useState("C01");
  const [message, setMessage] = useState("");
  const [languageMode, setLanguageMode] = useState<"REAL_AVA_LANGUAGE" | "DETERMINISTIC_CERTIFICATION">("REAL_AVA_LANGUAGE");
  const [busy, setBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [analysisFallback, setAnalysisFallback] = useState<{ title: string; report: string } | null>(null);
  const [defectSeverity, setDefectSeverity] = useState("QUALITY");
  const [defectNote, setDefectNote] = useState("");
  const mutationInFlight = useRef(false);
  useEffect(() => {
    let active = true;
    let retryTimer: number | undefined;
    const retryDelays = [1000, 2000, 3000, 5000];
    const load = (attempt: number) => void getScenarioLab().then((value) => {
      if (!active) return;
      setSnapshot(value);
      setError("");
    }).catch((reason) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : "Scenario API unavailable.");
      const delay = retryDelays[attempt];
      if (delay != null) retryTimer = window.setTimeout(() => load(attempt + 1), delay);
    });
    load(0);
    return () => {
      active = false;
      if (retryTimer != null) window.clearTimeout(retryTimer);
    };
  }, []);
  const run = (action: () => Promise<ScenarioLabSnapshot>, success = "") => {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setBusy(true); setError(""); setNotice("");
    void action().then((value) => { setSnapshot(value); if (success) setNotice(success); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Scenario action failed."))
      .finally(() => { mutationInFlight.current = false; setBusy(false); });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault(); const exact = message;
    if (!exact.trim() || !snapshot?.activeScenario || busy || mutationInFlight.current) return;
    setMessage(""); run(() => sendScenarioTurn(exact, languageMode));
  };
  if (!snapshot) return <><div className="test-chat-live-badges"><span>SYNTHETIC SCENARIO TEST</span></div>
    {error ? <div className="test-chat-error" role="alert">{error}</div> : <section className="test-chat-card"><p>Loading Session 5 Scenario Lab…</p></section>}</>;
  const active = snapshot.activeScenario;
  const latest = snapshot.turns[snapshot.turns.length - 1] as Record<string, unknown> | undefined;
  const state = active?.state || {};
  const latestAva = snapshot.transcript.filter((item) => item.role === "assistant").at(-1)?.content;
  const lifecycle = active?.lifecycle;
  const finishCurrentScenario = () => {
    if (!active || busy || mutationInFlight.current) return;
    if (lifecycle !== "COMPLETED" && lifecycle !== "SNAPSHOTTED") return;
    if (!window.confirm(
      `Finish ${active.scenario}?\n\nIts current attempt will be archived, its synthetic customer state reset and verified clean, and the scenario selector will be unlocked.`,
    )) return;
    const scenarioId = active.scenario;
    run(async () => {
      if (lifecycle === "COMPLETED") await snapshotScenario(active.scenario);
      const value = await resetScenario(active.scenario);
      const clean = await verifyScenarioClean();
      if (clean.result !== "VERIFIED_CLEAN") throw new Error("Scenario reset verification failed.");
      setNotice(`${scenarioId} finished and verified clean. Select the next scenario, then choose Prepare Scenario.`);
      return value;
    });
  };
  return <>
    <div className="test-chat-live-toolbar">
      <div className="test-chat-live-badges">{snapshot.badges.map((badge) => <span key={badge}>{badge}</span>)}</div>
      {snapshot.databaseEnvironment && <div className="test-chat-environment-identity">
        Scenario Lab DB: {snapshot.databaseEnvironment.databaseName} · Purpose: {snapshot.databaseEnvironment.purpose}
      </div>}
      <div className="test-chat-live-copy">{active && <>
        <button disabled={!snapshot.recovery?.retryEligible || busy} title={snapshot.recovery?.retryBlocker || undefined} onClick={(event) => {
          event.preventDefault(); event.stopPropagation();
          if (mutationInFlight.current) return;
          const turn = snapshot.recovery?.retryTurn; const exact = snapshot.recovery?.retryCustomerMessage || "";
          if (!window.confirm(`Retry Turn ${turn} using the exact same customer message?\n\n${exact}`)) return;
          const reason = window.prompt("Optional retry reason:", "Latest turn response requires repair retest.") || undefined;
          const recoveryOperationId = crypto.randomUUID();
          mutationInFlight.current = true;
          setMessage(""); setBusy(true); setRetryBusy(true); setError(""); setNotice("");
          void retryPreviousScenarioTurn(reason, recoveryOperationId).then((value) => {
            setSnapshot(value);
            const retried = value.turns[value.turns.length - 1] as Record<string, unknown> | undefined;
            setNotice(`TURN ${turn} RETRIED — ATTEMPT ${Number(retried?.turnAttempt || 2)}`);
          }).catch((reasonValue) => {
            const detail = reasonValue instanceof Error ? reasonValue.message : "unknown retry failure";
            setError(`RETRY FAILED — ${detail}`);
          }).finally(() => { mutationInFlight.current = false; setRetryBusy(false); setBusy(false); });
        }} type="button">{retryBusy ? `RETRYING TURN ${snapshot.recovery?.retryTurn || ""}...` : "Retry Previous Turn"}</button>
        <button disabled={lifecycle !== "RUNNING" || busy} onClick={(event) => {
          event.preventDefault(); event.stopPropagation();
          if (mutationInFlight.current) return;
          if (!window.confirm(`Restart ${active.scenario} from Turn 0?\n\nThe current attempt will be preserved as ABORTED_FOR_REPAIR.`)) return;
          const reason = window.prompt("Optional restart reason:", "Scenario trajectory requires a clean restart.") || undefined;
          run(() => restartEntireScenario(active.scenario, reason), `${active.scenario} restarted from Turn 0.`);
        }} type="button">Restart Entire Scenario</button>
      </>}
      <button disabled={!active} onClick={() => {
        if (!active) return;
        const scenarioId = active.scenario;
        setCopyStatus("idle"); setError(""); setNotice(""); setAnalysisFallback(null);
        void getFullScenarioAnalysis(scenarioId)
          .then(async (analysis) => {
            if (analysis.scenario.scenarioId !== scenarioId) {
              throw new Error(`Scenario analysis mismatch: selected ${scenarioId}, received ${analysis.scenario.scenarioId}.`);
            }
            const report = buildFullScenarioAnalysisReport(analysis);
            const title = `${analysis.scenario.scenarioId} Attempt ${analysis.scenario.scenarioAttempt}`;
            if (!navigator.clipboard?.writeText) {
              setAnalysisFallback({ title, report });
              setNotice(`Clipboard unavailable — Full Scenario Analysis displayed for ${title}.`);
              return false;
            }
            try {
              await navigator.clipboard.writeText(report);
              setNotice(`Full Scenario Analysis copied — ${title}`);
              return true;
            } catch {
              setAnalysisFallback({ title, report });
              setNotice(`Clipboard write failed — Full Scenario Analysis displayed for ${title}.`);
              return false;
            }
          })
          .then((copied) => { if (copied) { setCopyStatus("copied"); window.setTimeout(() => setCopyStatus("idle"), 1800); } })
          .catch((reason) => {
            setError(reason instanceof Error ? reason.message : "Scenario analysis copy failed.");
            setCopyStatus("failed");
          });
      }} type="button">{copyStatus === "copied" ? "Copied!" : "Copy Full Scenario Analysis"}</button>
      <span aria-live="polite">{copyStatus === "failed" ? "Copy failed" : ""}</span></div>
    </div>
    {analysisFallback && <div className="test-chat-modal-backdrop" role="presentation">
      <section aria-labelledby="scenario-analysis-fallback-title" aria-modal="true" className="test-chat-modal test-chat-analysis-fallback" role="dialog">
        <h2 id="scenario-analysis-fallback-title">Full Scenario Analysis — {analysisFallback.title}</h2>
        <p>Clipboard access was unavailable. Select and copy the complete report below.</p>
        <textarea aria-label="Full Scenario Analysis report" readOnly value={analysisFallback.report} />
        <div className="test-chat-modal-actions">
          <button onClick={() => setAnalysisFallback(null)} type="button">Close</button>
        </div>
      </section>
    </div>}
    <section className="test-chat-card test-chat-scenario-picker"><h2>Customer Scenario</h2><div>
      <select aria-describedby={active ? "scenario-selector-lock" : undefined} aria-label="Customer Scenario" disabled={Boolean(active) || busy} onChange={(event) => setSelected(event.target.value)} value={active?.scenario || selected}>
        {snapshot.scenarios.map((item) => <option key={item.scenario} value={item.scenario}>{item.scenario} — {item.description}</option>)}
      </select>
      <button disabled={Boolean(active) || busy} onClick={() => run(() => prepareScenario(selected))} type="button">Prepare Scenario</button>
      <label htmlFor="scenario-language-mode">Language</label>
      <select id="scenario-language-mode" disabled={busy} value={languageMode} onChange={(event) => setLanguageMode(event.target.value as typeof languageMode)}>
        <option value="REAL_AVA_LANGUAGE">REAL AVA LANGUAGE</option>
        <option value="DETERMINISTIC_CERTIFICATION">DETERMINISTIC CERTIFICATION</option>
      </select>
    </div>{active && <p id="scenario-selector-lock">{lifecycle === "RUNNING"
      ? `Scenario selector locked while ${active.scenario} is running. Complete it with a grade, then choose Finish Current Scenario.`
      : lifecycle === "COMPLETED" || lifecycle === "SNAPSHOTTED"
        ? `${active.scenario} is ready to finish. Choose Finish Current Scenario to archive, reset, verify clean, and unlock the selector.`
        : `${active.scenario} must be safely finalized before another scenario can be prepared.`}</p>}</section>
    {error && <div className="test-chat-error" role="alert">{error}</div>}{notice && <div className="test-chat-notice" role="status">{notice}</div>}
    {active ? <>
      <section className="test-chat-card test-chat-user"><h2>{active.scenario} — {active.name.replaceAll("_", " ")}</h2>
        <DiagnosticGrid values={{ scenarioAttempt: active.scenarioAttempt, economicState: active.economicState, buyerStatus: state.buyerStatus,
          buyerStage: state.buyerStage, valueTier: state.valueTier, purchases: state.purchaseCount,
          lifetimeSpend: state.lifetimeSpendMinor, ownership: state.ownershipCount,
          timeWasterRisk: state.timeWasterRisk, attention: state.attentionTier, effort: state.effortMode,
          retention: state.retentionLifecycle, commercialMomentum: state.commercialMomentum,
          purchaseIntent: state.activePurchaseIntent, session: state.activeSession }} /></section>
      <section className="test-chat-card"><h2>Conversation</h2><div className="test-chat-transcript">
        {!snapshot.transcript.length && <p className="test-chat-empty">No messages yet.</p>}
        {snapshot.transcript.map((item, index) => <p className={`test-chat-message test-chat-message--${item.role}`} key={`${item.role}-${index}`}><strong>{item.role === "user" ? "Customer" : "Ava"}:</strong> {item.content}</p>)}
      </div><form className="test-chat-form" onSubmit={submit}><label htmlFor="scenario-message">Customer</label><div><input id="scenario-message" maxLength={4000} onChange={(event) => setMessage(event.target.value)} placeholder="Type a customer message" value={message} /><button disabled={busy || lifecycle !== "RUNNING" || !message.trim()} type="submit">{busy ? "Sending…" : "Send"}</button></div></form></section>
      <section className="test-chat-card"><h2>AI Response</h2><div className="test-chat-response-badges"><span>SYNTHETIC SCENARIO</span><span>{languageMode.replaceAll("_", " ")}</span><span>{snapshot.transport}</span></div><p>{latestAva || "No response yet."}</p><small>REAL PROVIDER IS OPTIONAL · EXTERNAL DELIVERY REMAINS DISABLED</small></section>
      <section className="test-chat-card"><h2>State Changes This Turn</h2>{latest ? <DiagnosticGrid values={{ changes: latest.stateChangesThisTurn }} /> : <p>NO MATERIAL STATE CHANGE</p>}</section>
      <section className="test-chat-card"><h2>Decision Summary</h2>{snapshot.latestAnalysis ? <><DiagnosticGrid values={snapshot.latestAnalysis} omit={["commercialSummary"]} /><CommercialAnalysis summary={snapshot.latestAnalysis} /></> : <p>Not evaluated</p>}</section>
      <div className="test-chat-actions"><button disabled={!snapshot.simulatePurchaseEligible || busy} onClick={() => run(simulateScenarioPurchase, "TEST PURCHASE SIMULATED — NO REAL FANVUE TRANSACTION")} type="button">Simulate Provider Purchase</button>
        {(["PASS", "PASS_WITH_NOTES", "FAIL"] as const).map((grade) => <button disabled={lifecycle !== "RUNNING" || busy} key={grade} onClick={() => run(() => completeScenario(grade))} type="button">Complete {grade.replaceAll("_", " ")}</button>)}
        <button disabled={(lifecycle !== "COMPLETED" && lifecycle !== "SNAPSHOTTED") || busy} onClick={finishCurrentScenario} type="button">Finish Current Scenario</button>
      </div>
      {!snapshot.recovery?.retryEligible && snapshot.recovery?.retryBlocker &&
        <div className="test-chat-safety" role="status">{snapshot.recovery.retryBlocker}</div>}
      <section className="test-chat-card"><h2>Add Defect Note</h2><div className="test-chat-defect"><select aria-label="Defect severity" onChange={(event) => setDefectSeverity(event.target.value)} value={defectSeverity}><option>QUALITY</option><option>MAJOR</option><option>CRITICAL</option></select><input aria-label="Defect note" onChange={(event) => setDefectNote(event.target.value)} value={defectNote} /><button disabled={!defectNote.trim() || busy} onClick={() => run(() => addScenarioDefect(defectSeverity, defectNote), "Defect note saved.")} type="button">Add Defect Note</button></div></section>
      <details className="test-chat-card"><summary>Legacy Synthetic</summary><p>The legacy generic subscriber/whale controls are retained in code for later review, but disabled while Session 5 scenario certification is active.</p></details>
      <div className="test-chat-safety" role="status">TEST_TRANSPORT_NO_WAIT · No Telegram send · No Fanvue call</div>
    </> : <section className="test-chat-card"><p>Select a scenario and choose Prepare Scenario. No customer message is sent automatically.</p><details><summary>Legacy Synthetic</summary><p>The previous generic test-user workflow is retained for later developer review and is not the default Synthetic Test experience.</p></details></section>}
  </>;
}

function display(value: unknown): string {
  if (value == null || value === "") return "Not evaluated";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return Object.keys(value as object).length ? JSON.stringify(value) : "None";
  return String(value);
}

function DiagnosticGrid({ values, omit = [] }: { values: Record<string, unknown>; omit?: string[] }) {
  return <dl className="test-chat-decision">{Object.entries(values).filter(([key]) => key !== "rawDiagnostics" && !omit.includes(key)).map(([key, value]) =>
    <div key={key}><dt>{key.replace(/([A-Z])/g, " $1")}</dt><dd>{display(value)}</dd></div>)}</dl>;
}

const COMMERCIAL_SECTION_LABELS: Record<string, string> = {
  customerTemperature: "Customer Temperature",
  buyingSignals: "Buying Signals",
  resistance: "Resistance",
  purchaseCommerceState: "Purchase / Commerce State",
  cooldownPressure: "Cooldown / Pressure",
  currentOffer: "Current Offer",
  objectionRecovery: "Objection / Recovery",
  inventorySelection: "Inventory Selection",
  policyGate: "Controlling Gate",
  finalSalesDecision: "Final Sales Decision",
};

function CommercialAnalysis({ summary }: { summary: unknown }) {
  if (!summary || typeof summary !== "object" || (summary as Record<string, unknown>).status === "Not evaluated") return null;
  const values = summary as Record<string, unknown>;
  return <div className="test-chat-commercial-analysis">{Object.entries(COMMERCIAL_SECTION_LABELS).map(([key, label]) => {
    const section = values[key];
    return section && typeof section === "object" ? <section key={key}><h3>{label}</h3><DiagnosticGrid values={section as Record<string, unknown>} /></section> : null;
  })}</div>;
}

function LiveControlledTest({ snapshot, error }: { snapshot: LiveControlledSnapshot | null; error: string }) {
  const [selected, setSelected] = useState(0);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetPreview, setResetPreview] = useState<LiveControlledSnapshot["resetDryRun"] | null>(null);
  const [resetResult, setResetResult] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const turn = snapshot?.turns[selected] || snapshot?.turns[snapshot.turns.length - 1];
  if (!snapshot) return <>{error && <div className="test-chat-error" role="alert">{error}</div>}<section className="test-chat-card"><p>Loading controlled test observer…</p></section></>;
  return <>
    <div className="test-chat-live-toolbar">
      <div className="test-chat-live-badges"><span>LIVE CONTROLLED TEST</span><span>External Sends: Controlled</span></div>
      <div className="test-chat-live-copy">
        <button onClick={() => {
          setCopyStatus("idle");
          void navigator.clipboard.writeText(buildFullAnalysis(snapshot)).then(() => {
            setCopyStatus("copied"); window.setTimeout(() => setCopyStatus("idle"), 1800);
          }).catch(() => {
            setCopyStatus("failed"); window.setTimeout(() => setCopyStatus("idle"), 2500);
          });
        }} type="button">{copyStatus === "copied" ? "Copied!" : "Copy Full Analysis"}</button>
        <button disabled={!snapshot.resetDryRun.allowed} onClick={() => { setResetPreview(snapshot.resetDryRun); setConfirmReset(true); }} type="button">Reset Controlled Test</button>
        <span aria-live="polite">{copyStatus === "failed" ? "Copy failed" : ""}</span>
      </div>
    </div>
    <section className="test-chat-card test-chat-user"><h2>Controlled Telegram Test Customer</h2><DiagnosticGrid values={snapshot.customer} /></section>
    <section className="test-chat-card"><h2>Conversation</h2><div className="test-chat-transcript">
      {snapshot.conversation.length === 0 && <p>No persisted turns yet.</p>}
      {snapshot.conversation.map((item, index) => <div className={`test-chat-message test-chat-message--${item.role}`} key={`${item.providerMessageId}-${index}`}>
        <strong>{item.role === "user" ? "Customer" : "Ava"}:</strong> {item.content}
        <small>{item.timestamp || "Timestamp unavailable"} · Telegram #{item.providerMessageId ?? "unknown"} · {item.classification || "Not evaluated"}{item.replyOperationState ? ` · ${item.replyOperationState}` : ""}</small>
      </div>)}
    </div><div className="test-chat-live-input">Messages are sent only from the controlled Telegram account. This observer cannot send.</div></section>
    <section className="test-chat-card"><h2>Decision Timeline</h2><div className="test-chat-timeline">
      <table><thead><tr><th>Turn</th><th>Customer Message</th><th>Intent</th><th>Stage</th><th>Decision</th><th>Offer</th><th>PurchaseIntent</th></tr></thead><tbody>
        {snapshot.turns.map((item, index) => { const d = item.decision; return <tr className={turn?.turn === item.turn ? "is-selected" : ""} key={item.turn} onClick={() => setSelected(index)}>
          <td>{item.turn}</td><td>{item.customerMessage}</td><td>{display(d.intent)}</td><td>{display(d.relationshipStage)}</td><td>{display(d.salesBrainDecision)}</td><td>{display(d.sell)}</td><td>{display(d.purchaseIntentCreated)}</td></tr>; })}
      </tbody></table></div></section>
    <section className="test-chat-card"><h2>Decision Summary — Turn {turn?.turn || "—"}</h2>{turn ? <><DiagnosticGrid values={turn.decision} omit={["commercialSummary"]} /><CommercialAnalysis summary={turn.decision.commercialSummary} /></> : <p>Not evaluated</p>}</section>
    <section className="test-chat-card"><h2>Current Sales Brain State</h2><DiagnosticGrid values={snapshot.currentState} /></section>
    <section className="test-chat-card"><h2>Memory Diagnostics</h2><DiagnosticGrid values={snapshot.memory} /></section>
    <section className="test-chat-card"><h2>Time Context</h2><DiagnosticGrid values={snapshot.timeContext} /></section>
    <section className="test-chat-card"><h2>Response Pacing</h2><DiagnosticGrid values={snapshot.pacing} /></section>
    <section className="test-chat-card"><h2>Sleep / Wake</h2><DiagnosticGrid values={snapshot.sleep || { state: "NOT EVALUATED" }} /></section>
    <details className="test-chat-card"><summary>Reset Controlled Test</summary><div className="test-chat-reset-preview">
      <p><strong>{snapshot.resetDryRun.allowed ? "Safety checks pass" : "Reset blocked"}</strong>. No reset has been executed.</p>
      {snapshot.resetDryRun.blockers.length > 0 && <p>Blockers: {snapshot.resetDryRun.blockers.join(", ")}</p>}
      <h3>Would clear</h3><DiagnosticGrid values={snapshot.resetDryRun.wouldClear} /><h3>Would preserve</h3><ul>{snapshot.resetDryRun.wouldPreserve.map((item) => <li key={item}>{item}</li>)}</ul>
      <p>Available only before any controlled purchase/mapping.</p>
    </div></details>
    {confirmReset && <div className="test-chat-modal-backdrop" role="presentation"><section aria-modal="true" className="test-chat-modal" role="dialog">
      <h2>Confirm Reset Controlled Test</h2><h3>WILL RESET</h3><ul><li>controlled conversation</li><li>ordinary reply operations</li><li>decision history</li><li>prospect relationship/preferences</li><li>controlled identity observation</li></ul>
      <h3>WILL PRESERVE</h3><ul><li>controlled allowlist</li><li>workers</li><li>Fanvue test buyer</li><li>$3 test offering</li><li>all commerce</li><li>Content Vault</li><li>unrelated customers</li></ul>
      <p>Available only before any controlled purchase/mapping.</p>{resetResult && <p role="alert">{resetResult}</p>}
      <div className="test-chat-modal-actions"><button disabled={resetBusy} onClick={() => setConfirmReset(false)} type="button">Cancel</button><button disabled={resetBusy || !resetPreview?.allowed} onClick={() => {
        setResetBusy(true); setResetResult(""); void getControlledResetDryRun().then((fresh) => {
          setResetPreview(fresh); if (!fresh.allowed) throw new Error("Reset safety status changed; confirmation disabled.");
          return executeControlledReset();
        }).then(() => { setResetResult("Controlled test reset complete."); window.setTimeout(() => window.location.reload(), 500); })
          .catch((reason) => setResetResult(reason instanceof Error ? reason.message : "Reset blocked"))
          .finally(() => setResetBusy(false));
      }} type="button">{resetBusy ? "Rechecking…" : "Confirm Reset"}</button></div>
    </section></div>}
    <div className="test-chat-safety" role="status">Read-only observer · No AI generation · No sends · No commerce execution</div>
  </>;
}

function RecommendationDecision({
  diagnostics, learning, sell, salesReason,
}: {
  diagnostics?: RecommendationDiagnostics | null;
  learning?: CommerceLearningProfile | null;
  sell?: boolean;
  salesReason?: string | null;
}) {
  const ranked = diagnostics?.recommendationTrace || [];
  const selected = ranked.find((item) => item.selected);
  return <details className="test-chat-card test-chat-recommendation">
    <summary>Recommendation Decision</summary>
    <div className="test-chat-recommendation__body">
      <dl className="test-chat-decision">
        <div><dt>Sell</dt><dd>{sell == null ? "None" : sell ? "Yes" : "No"}</dd></div>
        <div><dt>Sales Brain reason</dt><dd>{label(salesReason)}</dd></div>
        <div><dt>Engine version</dt><dd>{label(diagnostics?.recommendationEngineVersion)}</dd></div>
        <div><dt>Eligible offerings</dt><dd>{diagnostics?.eligibleCount ?? 0}</dd></div>
        <div><dt>Selected offering</dt><dd>{selected?.title || "None"}</dd></div>
        <div><dt>Recommendation score</dt><dd>{selected ? selected.finalScore.toFixed(3) : "None"}</dd></div>
        <div><dt>Active Purchase Intent override</dt><dd>{diagnostics?.activeIntentApplied ? "Yes" : "No"}</dd></div>
        <div><dt>Explanation</dt><dd>{selected?.reason || diagnostics?.recommendationSummary || "No recommendation was selected."}</dd></div>
      </dl>
      {selected && <><h3>Score breakdown</h3>
        <table><thead><tr><th>Component</th><th>Raw score</th><th>Weight</th><th>Contribution</th><th>Evidence</th></tr></thead>
          <tbody>{selected.components.filter((item) => typeof item.rawValue === "number").map((item) =>
            <tr key={item.key}><td>{item.key.replaceAll("_", " ")}</td><td>{Number(item.rawValue).toFixed(3)}</td><td>{item.weight?.toFixed(2) || "—"}</td>
              <td>{item.weightedContribution.toFixed(3)}</td><td>{item.explanation}</td></tr>)}</tbody></table></>}
      <h3>Ranked candidates</h3>
      {ranked.length === 0 ? <p>No eligible ranked candidates.</p> :
        <ol>{ranked.slice(0, 5).map((item) => <li className={item.selected ? "is-selected" : ""} key={item.offeringId}>
          <strong>#{item.rank} {item.title}</strong> — {item.finalScore.toFixed(3)} ranking score
          <span>{item.reason}</span>
        </li>)}</ol>}
      <h3>Commerce learning profile</h3>
      {!learning ? <p>No observed commerce-learning history yet.</p> :
        <><p>{Math.round(learning.confidence * 100)}% profile confidence from {learning.evidenceCount} observed learning events.</p>
          <p>Preferred offering type: {learning.preferredOfferingType || "None"}</p>
          <pre>{JSON.stringify({ preferences: learning.preferences, outcomes: learning.outcomeCounts }, null, 2)}</pre></>}
    </div>
  </details>;
}
