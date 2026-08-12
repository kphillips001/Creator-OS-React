import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BackgroundOperationsProvider } from "../../background-operations/BackgroundOperationsContext";
import { GenerationWorkflowSections } from "./GenerationWorkflowSections";
import { getContentStudioGeneration, submitContentStudioGeneration } from "../../../infrastructure/api/contentStudioApi";

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

const request = { creativeMode: "premium_teaser", promptBatch: [], promptCount: 6,
  promptSource: "", promptSourceLabel: "Manual Prompt", provider: "seedream_5_0_pro" };

function NavigationHarness() {
  const [inStudio, setInStudio] = useState(true);
  return <>
    <button onClick={() => setInStudio((current) => !current)} type="button">
      {inStudio ? "Navigate away" : "Return to Content Studio"}
    </button>
    {inStudio ? <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
      activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
      request={request} workflow="manual" /> : <div>Another route</div>}
  </>;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("Autonomous Inspiration reconnection", () => {
  it("gives an explicit batch sole ownership of its Live Generation grid", async () => {
    const explicitOperation = {
      ...operation,
      operationType: "content_studio_generation",
      metadata: { request: { origin: "explicit_inspiration" } },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true,
      operations: String(input).includes("status=active") ? [explicitOperation] : [],
    }), { status: 200 })));
    vi.mocked(getContentStudioGeneration).mockResolvedValue({
      runId: explicitOperation.operationId, jobId: "job-1", promptPlanId: "plan-1",
      status: "running", message: "Processing image 3 of 4", provider: "Seedream",
      completedCount: 2, failedCount: 0, processedCount: 2, totalCount: 4,
      progress: 50, images: [{ index: 0, url: "/one" }, { index: 1, url: "/two" }],
    });
    const items = [
      { error: "", id: "one", imageUrl: "/one", jobId: "job-1", ordinal: 0, status: "completed" as const },
      { error: "", id: "two", imageUrl: "/two", jobId: "job-2", ordinal: 1, status: "completed" as const },
      { error: "", id: "three", imageUrl: "", jobId: null, ordinal: 2, status: "generating" as const },
      { error: "", id: "four", imageUrl: "", jobId: null, ordinal: 3, status: "pending" as const },
    ];

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 93, lastUsedAt: null } }} disabled={false}
        reconnectOrigins={["canonical_planner", "manual_creative_concept", "recreate_with_ava"]}
        request={request} workflow="manual" />
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 93, lastUsedAt: null } }} disabled={false}
        plannerBatchItems={items} plannerBatchProgress={{ completedIdeas: 2, currentIdeaIndex: 3,
          failedIdeas: 0, phase: "generating", totalIdeas: 4 }} plannerBatchRunning
        reconnectOrigins={["explicit_inspiration", "explicit_tags"]}
        request={{ ...request, creativeMode: "explicit", promptCount: 4 }} workflow="manual" />
    </BackgroundOperationsProvider>);

    await waitFor(() => expect(getContentStudioGeneration).toHaveBeenCalledTimes(1));
    const presentations = await screen.findAllByLabelText("Live Generation");
    expect(presentations).toHaveLength(1);
    expect(presentations[0]).toHaveTextContent("Generating idea 3 of 4");
    expect(presentations[0]).toHaveTextContent("Completed: 2");
    expect(presentations[0]).toHaveTextContent("Provider: Seedream");
    expect(screen.getAllByRole("img", { name: /Generated image/ })).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Waiting for generated image 3 of 4" })).toBeInTheDocument();
  });

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
    render(<BackgroundOperationsProvider pollMilliseconds={10}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
        onReconnect={onReconnect} request={request} workflow="autonomous" />
    </BackgroundOperationsProvider>);

    expect(await screen.findByLabelText("Live Generation")).toHaveTextContent("Processing image 3 of 6");
    expect(onReconnect).toHaveBeenCalledTimes(1);
    expect(getContentStudioGeneration).toHaveBeenCalledWith(operation.operationId);
  });

  it("reconnects a manual generation after route unmount and remount without resubmitting", async () => {
    let backendActive = false;
    const manualOperation = { ...operation, operationType: "content_studio_generation" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true,
      operations: String(input).includes("status=active") && backendActive ? [manualOperation] : [],
    }), { status: 200 })));
    vi.mocked(getContentStudioGeneration).mockResolvedValue({
      runId: manualOperation.operationId, jobId: "job-1", promptPlanId: "plan-1",
      status: "running", message: "Processing image 3 of 6", provider: "Seedream",
      completedCount: 2, failedCount: 0, processedCount: 2, totalCount: 6,
      progress: 33.3, images: [{ index: 0, url: "/one" }, { index: 1, url: "/two" }],
    });

    render(<BackgroundOperationsProvider pollMilliseconds={10}><NavigationHarness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Navigate away" }));
    const callsBeforeActivation = vi.mocked(globalThis.fetch).mock.calls.length;
    backendActive = true;
    await waitFor(() => expect(vi.mocked(globalThis.fetch).mock.calls.length).toBeGreaterThan(callsBeforeActivation));
    fireEvent.click(screen.getByRole("button", { name: "Return to Content Studio" }));

    const live = await screen.findByLabelText("Live Generation");
    await waitFor(() => expect(live).toHaveTextContent("Processing image 3 of 6"));
    expect(live).toHaveTextContent("2 of 6 Processed");
    expect(screen.getAllByRole("img", { name: /Generated image/ })).toHaveLength(2);
    expect(getContentStudioGeneration).toHaveBeenCalledWith(manualOperation.operationId);
    expect(submitContentStudioGeneration).not.toHaveBeenCalled();
  });

  it.each(["QUEUED", "WAITING_EXTERNAL"] as const)("reconnects a %s manual operation", async (status) => {
    const activeOperation = { ...operation, operationType: "content_studio_generation", status };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: String(input).includes("status=active") ? [activeOperation] : [],
    }), { status: 200 })));
    vi.mocked(getContentStudioGeneration).mockResolvedValue({
      runId: activeOperation.operationId, jobId: null, promptPlanId: "plan-1",
      status: "running", message: status === "QUEUED" ? "Generation queued" : "Waiting for provider",
      provider: "Seedream", completedCount: 0, failedCount: 0, processedCount: 0,
      totalCount: 6, progress: 0, images: [],
    });
    render(<BackgroundOperationsProvider pollMilliseconds={60_000}>
      <GenerationWorkflowSections context={{ status: "ready", creatorProfileExists: true,
        activeReference: { assetId: 7, lastUsedAt: null } }} disabled={false}
        request={request} workflow="manual" />
    </BackgroundOperationsProvider>);
    const live = await screen.findByLabelText("Live Generation");
    await waitFor(() => expect(live).toHaveTextContent(
      status === "QUEUED" ? "Generation queued" : "Waiting for provider",
    ));
    expect(submitContentStudioGeneration).not.toHaveBeenCalled();
  });
});
