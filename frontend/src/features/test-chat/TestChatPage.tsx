import { type FormEvent, useEffect, useState } from "react";

import {
  clearTestChat,
  newTestChat,
  resetTestChatMemory,
  sendTestChatMessage,
  TestChatApiError,
  type TestChatErrorDetails,
} from "../../infrastructure/api/testChatApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CommerceLearningProfile,
  RecommendationDiagnostics,
  TestChatSession,
} from "./types";
import "./test-chat.css";

const label = (value: string | null | undefined) => value || "None";

export function TestChatPage() {
  const [session, setSession] = useState<TestChatSession | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorDetails, setErrorDetails] = useState<TestChatErrorDetails | null>(null);

  const run = async (action: () => Promise<TestChatSession>) => {
    setBusy(true);
    setError("");
    setErrorDetails(null);
    try { setSession(await action()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Test Chat request failed."); }
    finally { setBusy(false); }
  };

  useEffect(() => { void run(newTestChat); }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!session || !value || busy) return;
    setMessage(""); setBusy(true); setError(""); setErrorDetails(null);
    void sendTestChatMessage(session.sessionId, value).then((turn) => setSession((current) => current ? {
      ...current,
      messages: [...current.messages, { role: "user", content: value }, { role: "assistant", content: turn.reply }],
      reply: turn.reply,
      decision: { ...turn },
    } : current)).catch((reason) => {
      if (reason instanceof TestChatApiError) setErrorDetails(reason.details);
      else setError(reason instanceof Error ? reason.message : "Test Chat request failed.");
    }).finally(() => setBusy(false));
  };

  return <section className="test-chat-page">
    <PageHeader title="Test Chat" description="Exercise the Sales Agent brain with a synthetic customer." />
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
        <dl className="test-chat-decision"><div><dt>Intent</dt><dd>{label(session.decision?.intent)}</dd></div><div><dt>Relationship</dt><dd>{label(session.decision?.relationship)}</dd></div><div><dt>Sell</dt><dd>{session.decision ? (session.decision.sell ? "YES" : "NO") : "None"}</dd></div><div><dt>Sales Brain decision</dt><dd>{label(session.decision?.customer_sales_decision)}</dd></div><div><dt>Sales Brain reason</dt><dd>{label(session.decision?.customer_sales_reason_code)}</dd></div><div><dt>Commerce policy</dt><dd>{label(session.decision?.commerce_execution_policy)}</dd></div><div><dt>Commerce prompt mode</dt><dd>{label(session.decision?.commerce_prompt_mode)}</dd></div><div><dt>Commerce mode</dt><dd>{label(session.decision?.commerce_mode)}</dd></div><div><dt>Compatibility mode</dt><dd>{session.decision ? (session.decision.compatibility_mode ? "Yes" : "No") : "None"}</dd></div><div><dt>Selection source</dt><dd>{label(session.decision?.selection_source)}</dd></div><div><dt>Delivery source</dt><dd>{label(session.decision?.delivery_source)}</dd></div><div><dt>Memory source</dt><dd>{label(session.decision?.memory_source)}</dd></div><div><dt>Eligibility source</dt><dd>{label(session.decision?.eligibility_source)}</dd></div><div><dt>Recommendation source</dt><dd>{label(session.decision?.recommendation_source)}</dd></div><div><dt>Legacy memory mutated</dt><dd>{session.decision ? (session.decision.legacy_memory_mutated ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy delivery used</dt><dd>{session.decision ? (session.decision.legacy_delivery_used ? "Yes" : "No") : "None"}</dd></div><div><dt>Authoritative offering selected</dt><dd>{session.decision ? (session.decision.authoritative_offering_selected ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy recommendation used</dt><dd>{session.decision ? (session.decision.legacy_recommendation_used ? "Yes" : "No") : "None"}</dd></div><div><dt>Legacy offer requested</dt><dd>{session.decision ? (session.decision.legacy_offer_requested ? "Yes" : "No") : "None"}</dd></div><div><dt>Commerce authorized</dt><dd>{session.decision ? (session.decision.commerce_offer_authorized ? "Yes" : "No") : "None"}</dd></div><div><dt>Final authorization</dt><dd>{session.decision ? (session.decision.final_offer_authorized ? "Yes" : "No") : "None"}</dd></div><div><dt>AI Provider</dt><dd>{label(session.decision?.provider_selected)}</dd></div><div><dt>Reason</dt><dd>{label(session.decision?.reason)}</dd></div><div><dt>Commerce lookup attempted</dt><dd>{session.decision ? (session.decision.commerce_lookup_attempted ? "Yes" : "No") : "None"}</dd></div><div><dt>Requested media type</dt><dd>{label(session.decision?.requested_media_type)}</dd></div><div><dt>Requested themes</dt><dd>{session.decision?.requested_themes?.length ? session.decision.requested_themes.join(", ") : "None"}</dd></div><div><dt>Offering selected</dt><dd>{session.decision ? (session.decision.offering_selected ? "Yes" : "No") : "None"}</dd></div><div><dt>Offering ID</dt><dd>{label(session.decision?.offering_id)}</dd></div><div><dt>Offering type</dt><dd>{label(session.decision?.offering_type)}</dd></div><div><dt>Title</dt><dd>{label(session.decision?.offering_title)}</dd></div><div><dt>Price</dt><dd>{session.decision?.price_minor != null ? new Intl.NumberFormat(undefined, { style: "currency", currency: session.decision.currency || "USD" }).format(session.decision.price_minor / 100) : "None"}</dd></div><div><dt>Primary Sales Channel</dt><dd>{label(session.decision?.primary_sales_channel)}</dd></div><div><dt>Provider</dt><dd>{label(session.decision?.provider)}</dd></div><div><dt>Fulfillable</dt><dd>{session.decision ? (session.decision.fulfillable ? "Yes" : "No") : "None"}</dd></div><div><dt>Recommendation reason</dt><dd>{label(session.decision?.recommendation_reason)}</dd></div><div><dt>No-offering reason</dt><dd>{label(session.decision?.no_offering_reason)}</dd></div><div><dt>Delivery URL</dt><dd>{session.decision?.delivery_url ? <a href={session.decision.delivery_url} rel="noreferrer" target="_blank">{session.decision.delivery_url}</a> : "None"}</dd></div><div><dt>Legacy Product</dt><dd>{label(session.decision?.product)}</dd></div><div><dt>Legacy Asset</dt><dd>{label(session.decision?.asset)}</dd></div></dl>
      </section>
      <RecommendationDecision
        diagnostics={session.decision?.recommendation_diagnostics}
        learning={session.decision?.commerce_learning_profile}
        sell={session.decision?.sell}
        salesReason={session.decision?.customer_sales_reason_code}
      />
      <div className="test-chat-safety" role="status">🚫 External Sends Disabled</div>
    </>}
  </section>;
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
