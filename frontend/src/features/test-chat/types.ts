export type TestChatUser = {
  name: string;
  relationship: string;
  buyerTier: string;
};

export type TestChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type TestChatDecision = {
  intent: string;
  relationship: string;
  sell: boolean;
  reason: string;
  product: string | null;
  asset: string | null;
};

export type TestChatTurn = TestChatDecision & { reply: string };

export type TestChatSession = {
  sessionId: string;
  testUser: TestChatUser;
  messages: TestChatMessage[];
  reply?: string;
  decision?: TestChatDecision;
  externalSendsDisabled: boolean;
};
