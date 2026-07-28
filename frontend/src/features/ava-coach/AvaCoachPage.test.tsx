import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AvaCoachPage, coachGreeting } from "./AvaCoachPage";

const dashboard = {
  overview: {
    totalConversationsReviewed: 2, totalMessagesReviewed: 12,
    averageConversationLength: 6, returningVisitors: 1,
    topicsDiscussed: [{ topic: "hiking", mentions: 4, messageCount: 4, conversationCount: 2, messageIds: [1, 2], trend: null }],
    conversationEndings: { ava: 1, visitor: 1, unknown: 0 },
    questionsAsked: 3, conversationContinuationRate: 75, inboundMessages: 6, outboundMessages: 6,
  },
  snapshot: { snapshot_id: "snapshot-1", created_at: "2026-07-26T12:00:00Z", period_start: "2026-07-20T12:00:00Z", period_end: "2026-07-26T12:00:00Z" },
  insights: [
    { insight_type: "POSITIVE_STRENGTH", title: "Ava kept conversations moving", description: "Visitors replied.", evidence: { sampleSize: 8 }, confidence: 0.8 },
    { insight_type: "QUESTION_PATTERN", title: "Consecutive questions observed", description: "Observed pattern.", evidence: { messageIdPairs: [[1, 2]], sampleSize: 2 }, confidence: 0.8 },
  ],
  recommendations: [{
    recommendation_id: "recommendation-1", title: "Reduce consecutive questions",
    description: "Ask one question.", evidence: { messageIdPairs: [[1, 2]], sampleSize: 2 },
    confidence: 0.8, expected_impact: "Clearer response space.",
    status: "PENDING", version_label: "Ava v1.1", approved_at: null,
  }],
  appliedImprovements: [],
  versions: [
    { version_id: "v1", version_label: "Ava v1.0", status: "BASELINE", notes: "Baseline" },
    { version_id: "v2", version_label: "Ava v1.1", status: "DRAFT", notes: "Not activated" },
  ],
  observationalOnly: true,
};

afterEach(() => vi.restoreAllMocks());

it.each([
  [new Date(2026, 0, 1, 8), "Good morning, Kevin."],
  [new Date(2026, 0, 1, 14), "Good afternoon, Kevin."],
  [new Date(2026, 0, 1, 20), "Good evening, Kevin."],
])("uses local greeting", (date, expected) => expect(coachGreeting(date)).toBe(expected));

it("renders strengths, behavior evidence, topics, and draft version semantics", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(dashboard), { status: 200 }));
  render(<AvaCoachPage />);
  expect(await screen.findByRole("heading", { name: "Conversation Health" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What Ava Did Well" })).toBeInTheDocument();
  expect(screen.getByText("Ava kept conversations moving")).toBeInTheDocument();
  expect(screen.getByText("2 conversations · 4 messages")).toBeInTheDocument();
  expect(screen.getByText(/no effect until a future personality-version activation/i)).toBeInTheDocument();
});

it("edits a pending recommendation without touching runtime APIs", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(dashboard), { status: 200 }));
  render(<AvaCoachPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Edit/ }));
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Edited title" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ava-coach/recommendations/recommendation-1",
    expect.objectContaining({ method: "PATCH" }),
  ));
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("prompts"))).toBe(false);
});

it("requires approval confirmation and uses approved-for-version language", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(dashboard), { status: 200 }));
  render(<AvaCoachPage />);
  fireEvent.click(await screen.findByRole("button", { name: /^Approve$/ }));
  expect(screen.getByRole("dialog")).toHaveTextContent(/live personality and runtime behavior will not change/i);
  fireEvent.click(screen.getByRole("button", { name: /Approve Recommendation/ }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/ava-coach/recommendations/recommendation-1/approve",
    expect.objectContaining({ method: "POST" }),
  ));
});

it("prevents duplicate analysis clicks and reports completion counts", async () => {
  let resolveAnalysis!: (value: Response) => void;
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(dashboard), { status: 200 }))
    .mockImplementationOnce(() => new Promise((resolve) => { resolveAnalysis = resolve; }));
  render(<AvaCoachPage />);
  const button = await screen.findByRole("button", { name: /Run Conversation Analysis/ });
  fireEvent.click(button); fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  resolveAnalysis(new Response(JSON.stringify(dashboard), { status: 200 }));
  expect(await screen.findByText(/Analysis complete: 2 conversations and 12 messages/)).toBeInTheDocument();
});
