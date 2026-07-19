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
import type { TestChatSession } from "./types";
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
      decision: { intent: turn.intent, relationship: turn.relationship, sell: turn.sell, reason: turn.reason, product: turn.product, asset: turn.asset },
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
        <dl className="test-chat-decision"><div><dt>Intent</dt><dd>{label(session.decision?.intent)}</dd></div><div><dt>Relationship</dt><dd>{label(session.decision?.relationship)}</dd></div><div><dt>Sell</dt><dd>{session.decision ? (session.decision.sell ? "YES" : "NO") : "None"}</dd></div><div><dt>Reason</dt><dd>{label(session.decision?.reason)}</dd></div><div><dt>Product</dt><dd>{label(session.decision?.product)}</dd></div><div><dt>Asset</dt><dd>{label(session.decision?.asset)}</dd></div></dl>
      </section>
      <div className="test-chat-safety" role="status">🚫 External Sends Disabled</div>
    </>}
  </section>;
}
