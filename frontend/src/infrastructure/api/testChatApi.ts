import type { TestChatSession, TestChatTurn } from "../../features/test-chat/types";
import { environment } from "../config/environment";

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
    intent: string; relationship: string; sell: boolean; reason: string;
    product: string | null; asset: string | null;
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
  const response = await fetch(`${environment.apiBaseUrl}/developer/test-chat${path}`, {
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
  const response = await fetch(`${environment.apiBaseUrl}/developer/test-chat/turns`, {
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
