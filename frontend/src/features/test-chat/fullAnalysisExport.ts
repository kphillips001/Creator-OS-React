import type { LiveControlledSnapshot } from "../../infrastructure/api/testChatApi";

const SECRET_KEY = /(password|secret|token|apikey|apihash|authkey|sessionkey|sessionsecret|sessionpath|credential|cookie|phonecodehash)/i;
const SECRET_VALUE = /^(bearer\s+|basic\s+)|([?&](token|api_key|key|secret|signature)=)/i;

export function redactObserverSnapshot(value: unknown, key = ""): unknown {
  if (SECRET_KEY.test(key.replace(/[^a-z0-9]/gi, ""))) return "[REDACTED]";
  if (Array.isArray(value)) return value.map((item) => redactObserverSnapshot(item));
  if (value && typeof value === "object") return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([childKey, child]) =>
      [childKey, redactObserverSnapshot(child, childKey)]),
  );
  if (typeof value === "string" && SECRET_VALUE.test(value)) return "[REDACTED]";
  return value;
}

function scalar(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "NOT PROVIDED";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value || '""';
  return String(value);
}

export function serializeDiagnostic(value: unknown, indent = 0): string {
  const prefix = "  ".repeat(indent);
  if (Array.isArray(value)) {
    if (!value.length) return `${prefix}[]`;
    return value.map((item, index) => {
      if (item && typeof item === "object") return `${prefix}- [${index + 1}]\n${serializeDiagnostic(item, indent + 1)}`;
      return `${prefix}- ${scalar(item)}`;
    }).join("\n");
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return `${prefix}{}`;
    return entries.map(([key, child]) => {
      if (child && typeof child === "object") return `${prefix}- ${key}:\n${serializeDiagnostic(child, indent + 1)}`;
      return `${prefix}- ${key}: ${scalar(child)}`;
    }).join("\n");
  }
  return `${prefix}${scalar(value)}`;
}

const section = (title: string, value: unknown) => `## ${title}\n\n${serializeDiagnostic(value)}\n`;

function conversation(snapshot: Record<string, any>): string {
  if (!snapshot.turns?.length) return "No persisted turns.\n";
  return snapshot.turns.map((turn: Record<string, any>) => `### Turn ${turn.turn}\n\nCustomer:\n${
    turn.customerMessagePersisted ? turn.customerMessage : "[Unavailable — predates durable inbound capture]"
  }\n\nAva:\n${turn.reply || "[No persisted response]"}\n\nDiagnostics:\n${serializeDiagnostic({
    operationId: turn.operationId,
    inboundTelegramMessageId: turn.inboundProviderMessageId,
    outboundTelegramMessageId: turn.outboundProviderMessageId,
    inboundReceivedAt: turn.receivedAt,
    generationCompletedAt: turn.generatedAt,
    outboundConfirmedAt: turn.confirmedAt,
    resultType: turn.classification,
    replyOperationState: turn.replyOperationState,
    completeTurn: turn,
  })}\n`).join("\n");
}

function timeline(snapshot: Record<string, any>): string {
  const header = "| Turn | Customer Message | Intent | Stage | Decision | Offer | PurchaseIntent |\n| --- | --- | --- | --- | --- | --- | --- |";
  const rows = (snapshot.turns || []).map((turn: Record<string, any>) => {
    const decision = turn.decision || {};
    const text = String(turn.customerMessage || "").replaceAll("|", "\\|").replaceAll("\n", " ");
    return `| ${turn.turn} | ${text} | ${scalar(decision.intent)} | ${scalar(decision.relationshipStage)} | ${scalar(decision.salesBrainDecision)} | ${scalar(decision.sell)} | ${scalar(decision.purchaseIntentCreated)} |`;
  });
  return `${header}\n${rows.join("\n")}\n\nComplete Timeline Objects:\n${serializeDiagnostic(snapshot.turns || [])}\n`;
}

export function buildFullAnalysis(snapshot: LiveControlledSnapshot, generatedAt = new Date()): string {
  const safe = redactObserverSnapshot(snapshot) as Record<string, any>;
  const scope = safe.ordinaryReplyOperations?.[0]?.telegramAccountScope || "AVA_TELETHON_PRIVATE";
  const blocks = [
    "# Creator-OS Live Controlled Test — Full Analysis",
    `Snapshot Generated At: ${generatedAt.toISOString()}\nMode: LIVE CONTROLLED TEST\nControlled Scope: ${scope}`,
    section("Controlled Customer", safe.customer),
    `## Conversation\n\n${conversation(safe)}`,
    `## Decision Timeline\n\n${timeline(safe)}`,
    ...(safe.turns || []).flatMap((turn: Record<string, any>) => {
      const { commercialSummary, ...decision } = turn.decision || {};
      return [
        section(`Decision Summary — Turn ${turn.turn}`, decision),
        section(`Commercial Summary — Turn ${turn.turn}`, commercialSummary || { status: "NOT EVALUATED" }),
      ];
    }),
    section("Current Sales Brain State", safe.currentState),
    section("Recommendation Decision", safe.recommendationDecision),
    section("Commerce State", safe.commerceState),
    section("Memory Diagnostics", safe.memory),
    section("Time Context", safe.timeContext),
    section("Sleep / Wake", safe.sleep || { state: "NOT EVALUATED" }),
    section("Response Pacing", { current: safe.pacing, perTurn: (safe.turns || []).map((turn: any) => ({
      turn: turn.turn, receivedAt: turn.receivedAt, generatedAt: turn.generatedAt,
      confirmedAt: turn.confirmedAt, operation: (safe.ordinaryReplyOperations || []).find((item: any) => item.operationId === turn.operationId),
    })) }),
    section("Ordinary Reply Operations", safe.ordinaryReplyOperations),
    section("Identity Diagnostics", safe.identityDiagnostics),
    section("Fingerprint Diagnostics", safe.fingerprintDiagnostics),
    section("Session Diagnostics", safe.sessionDiagnostics),
    section("Purchase Acknowledgement", safe.purchaseAcknowledgement),
    section("Controlled Test Offering", safe.controlledTestOffering),
    section("Runtime Safety", safe.runtimeSafety),
    "## Raw Safe Observer Snapshot\n\n```json\n" + JSON.stringify(safe, null, 2) + "\n```",
  ];
  return blocks.join("\n\n");
}
