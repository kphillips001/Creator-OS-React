import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackgroundOperationsProvider } from "../../background-operations/BackgroundOperationsContext";
import { GenerationWorkflowSections } from "./GenerationWorkflowSections";
import { getContentStudioGeneration } from "../../../infrastructure/api/contentStudioApi";

vi.mock("../../../infrastructure/api/contentStudioApi", () => ({
  getContentStudioGeneration: vi.fn(),
  submitAutonomousInspiration: vi.fn(),
  submitContentStudioGeneration: vi.fn(),
}));

const operation = {
  operationId: "66d8aa08-fdb5-4ec1-98eb-ef203fc99826",
  operationType: "content_studio_autonomous_inspiration",
  originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
  status: "RUNNING", progressCurrent: 2, progressTotal: 6, progressPercent: 33.3,
  currentStage: "GENERATING", stageMessage: "Processing image 3 of 6",
  createdAt: "2026-08-05T12:00:00Z", startedAt: "2026-08-05T12:00:01Z",
  completedAt: null, resultLocation: "/studio/content", resultReference: "job-1",
  errorCode: null, errorMessage: null, cancellationSupported: false, metadata: {},
};

afterEach(() => vi.restoreAllMocks());

describe("Autonomous Inspiration reconnection", () => {
  it("rediscovers the durable operation and restores Live Generation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: String(input).includes("status=active") ? [operation] : [],
    }), { status: 200 })));
    vi.mocked(getContentStudioGeneration).mockResolvedValue({
      runId: operation.operationId, jobId: "job-1", promptPlanId: "plan-1",
      status: "running", message: "Processing image 3 of 6", provider: "Seedream",
      completedCount: 2, failedCount: 0, processedCount: 2, totalCount: 6,
      progress: 33.3, images: [{ index: 0, url: "/one" }, { index: 1, url: "/two" }],
    });
    const request = { creativeMode: "premium_teaser", promptBatch: [], promptCount: 6,
      promptSource: "", promptSourceLabel: "Manual Prompt", provider: "seedream_5_0_pro" };
    render(<BackgroundOperationsProvider pollMilliseconds={60_000}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
        request={request} workflow="autonomous" />
    </BackgroundOperationsProvider>);
    expect(await screen.findByLabelText("Live Generation")).toHaveTextContent("Processing image 3 of 6");
    await waitFor(() => expect(getContentStudioGeneration).toHaveBeenCalledWith(operation.operationId));
    expect(screen.getAllByRole("img", { name: /Generated image/ })).toHaveLength(2);
  });

  it("does not restore a completed operation from recent history", async () => {
    const completed = { ...operation, status: "SUCCEEDED", progressCurrent: 6,
      progressPercent: 100, currentStage: "COMPLETE", completedAt: "2026-08-05T12:01:00Z" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: String(input).includes("status=recent") ? [completed] : [],
    }), { status: 200 })));
    const request = { creativeMode: "premium_teaser", promptBatch: [], promptCount: 6,
      promptSource: "", promptSourceLabel: "Manual Prompt", provider: "seedream_5_0_pro" };
    render(<BackgroundOperationsProvider pollMilliseconds={60_000}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
        request={request} workflow="autonomous" />
    </BackgroundOperationsProvider>);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
    expect(getContentStudioGeneration).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Live Generation")).not.toBeInTheDocument();
  });

  it("waits for a later active refresh instead of consuming reconnect on an empty snapshot", async () => {
    let activeReads = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const active = String(input).includes("status=active");
      if (active) activeReads += 1;
      return Promise.resolve(new Response(JSON.stringify({
        success: true,
        operations: active && activeReads > 1 ? [operation] : [],
      }), { status: 200 }));
    });
    vi.mocked(getContentStudioGeneration).mockResolvedValue({
      runId: operation.operationId, jobId: "job-1", promptPlanId: "plan-1",
      status: "running", message: "Processing image 3 of 6", provider: "Seedream",
      completedCount: 2, failedCount: 0, processedCount: 2, totalCount: 6,
      progress: 33.3, images: [{ index: 0, url: "/one" }, { index: 1, url: "/two" }],
    });
    const onReconnect = vi.fn();
    const request = { creativeMode: "premium_teaser", promptBatch: [], promptCount: 6,
      promptSource: "", promptSourceLabel: "Manual Prompt", provider: "seedream_5_0_pro" };
    render(<BackgroundOperationsProvider pollMilliseconds={10}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
        onReconnect={onReconnect} request={request} workflow="autonomous" />
    </BackgroundOperationsProvider>);

    expect(await screen.findByLabelText("Live Generation")).toHaveTextContent("Processing image 3 of 6");
    expect(onReconnect).toHaveBeenCalledTimes(1);
    expect(getContentStudioGeneration).toHaveBeenCalledWith(operation.operationId);
  });
});
