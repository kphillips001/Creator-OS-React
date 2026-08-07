import { act, createRef } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GenerationWorkflowSections, type GenerationWorkflowHandle } from "./GenerationWorkflowSections";
import { getContentStudioGeneration, submitContentStudioGeneration } from "../../../infrastructure/api/contentStudioApi";

vi.mock("../../../infrastructure/api/contentStudioApi", () => ({
  getContentStudioGeneration: vi.fn(), submitAutonomousInspiration: vi.fn(), submitContentStudioGeneration: vi.fn(),
}));

const context = { status: "ready" as const, creatorProfileExists: true, activeReference: { assetId: 7, lastUsedAt: null } };
const request = { creativeMode: "premium_teaser", promptBatch: [], promptCount: 1, promptSource: "", promptSourceLabel: "Manual Prompt", provider: "seedream_5_0_pro" };
const override = { creativeMode: "premium_teaser", origin: "recreate_with_ava" as const, promptBatch: ["canonical prompt"], promptCount: 1, promptSource: "structured direction", promptSourceLabel: "Enhanced Tags", provider: "seedream_5_0_pro" };

describe("GenerationWorkflowSections request-aware gate", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); vi.mocked(submitContentStudioGeneration).mockResolvedValue("run-1"); vi.mocked(getContentStudioGeneration).mockResolvedValue({ runId: "run-1", jobId: "job-1", promptPlanId: "plan-1", status: "succeeded", message: "Complete", provider: "Seedream", completedCount: 1, failedCount: 0, processedCount: 1, totalCount: 1, progress: 100, images: [{ index: 0, url: "/image" }] }); });
  afterEach(() => vi.useRealTimers());

  it("submits a complete override even when ordinary manual authoring is disabled", async () => {
    const ref = createRef<GenerationWorkflowHandle>();
    render(<GenerationWorkflowSections context={context} disabled request={request} ref={ref} workflow="manual" />);
    let resultPromise!: ReturnType<GenerationWorkflowHandle["generateWithResult"]>;
    await act(async () => { resultPromise = ref.current!.generateWithResult(override); await Promise.resolve(); });
    expect(submitContentStudioGeneration).toHaveBeenCalledWith(expect.objectContaining({ promptBatch: ["canonical prompt"], promptSource: "structured direction", provider: "seedream_5_0_pro" }));
    expect(document.body).toHaveTextContent("Generating Ava recreation...");
    expect(document.querySelectorAll(".generation-live__slot")).toHaveLength(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    await expect(resultPromise).resolves.toMatchObject({ accepted: true, stage: "complete", status: "completed" });
  });

  it("blocks incomplete overrides before the generation POST", async () => {
    const ref = createRef<GenerationWorkflowHandle>();
    render(<GenerationWorkflowSections context={context} disabled request={request} ref={ref} workflow="manual" />);
    await expect(ref.current!.generateWithResult({ ...override, promptBatch: [] })).resolves.toMatchObject({ accepted: false, stage: "gate", status: "blocked" });
    expect(submitContentStudioGeneration).not.toHaveBeenCalled();
  });

  it("reports a failed POST at the submission stage", async () => {
    vi.mocked(submitContentStudioGeneration).mockRejectedValueOnce(new Error("Safe submission error"));
    const ref = createRef<GenerationWorkflowHandle>();
    render(<GenerationWorkflowSections context={context} disabled request={request} ref={ref} workflow="manual" />);
    await expect(ref.current!.generateWithResult(override)).resolves.toMatchObject({ accepted: false, reason: "Safe submission error", stage: "submission", status: "failed" });
  });

  it("reports an accepted provider failure at the provider stage", async () => {
    vi.mocked(getContentStudioGeneration).mockResolvedValueOnce({ runId: "run-1", jobId: "job-1", promptPlanId: "plan-1", status: "failed", message: "Provider generation failed.", provider: "Seedream", completedCount: 0, failedCount: 1, processedCount: 1, totalCount: 1, progress: 100, images: [] });
    const ref = createRef<GenerationWorkflowHandle>();
    render(<GenerationWorkflowSections context={context} disabled request={request} ref={ref} workflow="manual" />);
    let resultPromise!: ReturnType<GenerationWorkflowHandle["generateWithResult"]>;
    await act(async () => { resultPromise = ref.current!.generateWithResult(override); await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    await expect(resultPromise).resolves.toMatchObject({ accepted: true, reason: "Provider generation failed.", stage: "provider", status: "failed" });
  });

  it("briefly shows a failed terminal state and then clears the Live Generation presentation", async () => {
    vi.mocked(getContentStudioGeneration).mockResolvedValueOnce({ runId: "run-1", jobId: "job-1", promptPlanId: "plan-1", status: "failed", message: "Provider generation failed.", provider: "Seedream", completedCount: 0, failedCount: 1, processedCount: 1, totalCount: 1, progress: 100, images: [] });
    const onStartNewGeneration = vi.fn();
    const ref = createRef<GenerationWorkflowHandle>();
    render(<GenerationWorkflowSections context={context} disabled request={request} ref={ref}
      workflow="manual" onStartNewGeneration={onStartNewGeneration} />);
    let resultPromise!: ReturnType<GenerationWorkflowHandle["generateWithResult"]>;
    await act(async () => { resultPromise = ref.current!.generateWithResult(override); await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    await expect(resultPromise).resolves.toMatchObject({ status: "failed" });
    expect(screen.getByLabelText("Live Generation")).toHaveTextContent("Provider generation failed.");

    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(screen.queryByLabelText("Live Generation")).not.toBeInTheDocument();
    expect(onStartNewGeneration).toHaveBeenCalledTimes(1);
  });
});
