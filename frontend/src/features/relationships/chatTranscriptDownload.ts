import type { Relationship, RelationshipMessage } from "./api";
import { OPERATOR_TIME_ZONE } from "./chatTime";

const stamp = (value: string | Date, includeZone = false) =>
  new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZone: OPERATOR_TIME_ZONE,
    ...(includeZone ? { timeZoneName: "short" as const } : {}),
  }).format(new Date(value));

export function transcriptFilename(name: string, now = new Date()) {
  const safe = name.normalize("NFKD").replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "").toLowerCase() || "conversation";
  const date = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: OPERATOR_TIME_ZONE,
  }).format(now);
  return `creator-os-chat-${safe}-${date}.txt`;
}

export function buildChatTranscript(
  person: Pick<Relationship, "displayName" | "username">,
  messages: RelationshipMessage[], exportedAt = new Date(),
) {
  const header = [
    "Creator-OS Chat Transcript",
    `Relationship: ${person.displayName}`,
    ...(person.username ? [`Username: @${person.username}`] : []),
    `Exported: ${stamp(exportedAt, true)}`,
    "--------------------------------------------------",
  ];
  const body = [...messages]
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map((message) =>
      `[${stamp(message.timestamp)}] ${message.direction === "CUSTOMER" ? "CUSTOMER" : "AVA"}:\n${message.content}`,
    );
  return [...header, "", ...body.flatMap((value) => [value, ""])].join("\n").trimEnd() + "\n";
}

export function saveChatTranscript(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
