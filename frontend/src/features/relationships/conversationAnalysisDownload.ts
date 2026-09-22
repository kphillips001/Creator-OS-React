import type {ConversationAnalysisResponse, RelationshipMessage} from "./api";

export type ConversationAnalysisDownloadContext = {
  displayName?: string | null;
  username?: string | null;
  personKey: string;
  transcript?: RelationshipMessage[];
};

const text = (value: unknown) => String(value ?? "").trim();
const label = (value: unknown) => text(value).replaceAll("_", " ");
const bullet = (name: string, value: unknown) => `- **${name}:** ${text(value) || "—"}`;

export function sanitizeAnalysisFilenamePart(value: string): string {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/-+/g, "-")
    .replace(/^[ ._-]+|[ ._-]+$/g, "").toLowerCase() || "relationship";
}

export function conversationAnalysisFilename(analysis: ConversationAnalysisResponse, context: ConversationAnalysisDownloadContext): string {
  const identity = context.displayName || context.username || context.personKey;
  const date = /^\d{4}-\d{2}-\d{2}/.exec(analysis.analysis.analyzedAt || "")?.[0] || "analysis";
  return `creator-os-chat-analysis-${sanitizeAnalysisFilenamePart(identity)}-${date}.md`;
}

export function serializeConversationAnalysisMarkdown(response: ConversationAnalysisResponse, context: ConversationAnalysisDownloadContext): string {
  const {analysis} = response;
  const lines = ["# Creator-OS Chat Analysis", "", "## Customer / Relationship", "",
    bullet("Customer", context.displayName || context.personKey),
    ...(context.username ? [bullet("Username", `@${context.username.replace(/^@/, "")}`)] : []),
    bullet("Relationship", context.personKey), bullet("Analysis ID", response.analysisId),
    bullet("Analysis timestamp", analysis.analyzedAt), bullet("State", response.staleState),
    bullet("Schema", analysis.schemaVersion), "", "## Summary", "",
    bullet("Overall quality", analysis.overallQuality), bullet("Validated scope", label(analysis.validatedScope)),
    bullet("Global repair candidate", analysis.globalRepairCandidate ? "Yes" : "No"), "",
    analysis.conversationSummary || "—", "", "### Operator Summary", "", analysis.operatorSummary || "—", "", "## Findings", ""];
  if (!response.findings.length) lines.push("No findings.", "");
  response.findings.forEach((finding, index) => lines.push(
    `### ${index + 1}. ${label(finding.category) || "Finding"}`, "", bullet("Finding ID", finding.findingId),
    bullet("Target message", finding.targetMessageReference), bullet("Severity", finding.severity),
    bullet("Root cause", label(finding.rootCauseCategory)), bullet("Validated scope", label(finding.validatedScope)),
    bullet("Proposed scope", label(finding.proposedScope)), bullet("Confidence", `${Math.round(finding.confidence * 100)}%`),
    bullet("Similar cases", finding.similarCaseCount), bullet("Repair candidate", finding.repairCandidate ? "Yes" : "No"),
    bullet("Authority conflict", finding.authorityConflict ? "Yes" : "No"), "", "#### What Happened", "",
    finding.whatHappened || "—", "", "#### Why It Is Problematic", "", finding.whyItIsProblematic || "—", "",
    "#### Authoritative Evidence", "", finding.authoritativeEvidenceSummary || "—", "", "#### Suggested Correction", "",
    finding.suggestedCorrection || "—", ""));
  lines.push("## Similar Case Diagnostics", "", bullet("Similar case count", response.similarCaseSummary.similarCaseCount),
    bullet("Search basis", label(response.similarCaseSummary.searchBasis)));
  if (response.similarCaseSummary.relationshipReferences?.length) {
    lines.push("", "### Relationship References", "");
    response.similarCaseSummary.relationshipReferences.forEach((value) => lines.push(`- ${value}`));
  }
  if (context.transcript?.length) {
    lines.push("", "## Analyzed Conversation Context", "");
    context.transcript.forEach((message) => {
      const speaker = message.direction === "AVA" ? "Ava" : context.displayName || "Customer";
      const details = [message.timestamp, message.telegramMessageId != null ? `Telegram ${message.telegramMessageId}` : null, message.messageType].filter(Boolean).join(" · ");
      lines.push(`### ${speaker}${details ? ` — ${details}` : ""}`, "", message.content || "[No text content]", "");
    });
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

export function downloadConversationAnalysis(response: ConversationAnalysisResponse, context: ConversationAnalysisDownloadContext): void {
  const url = URL.createObjectURL(new Blob([serializeConversationAnalysisMarkdown(response, context)], {type: "text/markdown;charset=utf-8"}));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = conversationAnalysisFilename(response, context); anchor.click();
  URL.revokeObjectURL(url);
}
