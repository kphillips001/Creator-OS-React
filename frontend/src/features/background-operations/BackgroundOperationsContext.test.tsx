import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackgroundOperationsProvider, useBackgroundOperations } from "./BackgroundOperationsContext";

const running = {
  operationId: "operation-1", operationType: "content_studio_generation",
  originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "1",
  status: "RUNNING", progressCurrent: 1, progressTotal: 3, progressPercent: 33,
  currentStage: "GENERATING", stageMessage: "Generating image 2", createdAt: "2026-08-05T12:00:00Z",
  startedAt: "2026-08-05T12:00:01Z", completedAt: null, resultLocation: "/content/studio",
  resultReference: "job-1", errorCode: null, errorMessage: null, cancellationSupported: false, metadata: {},
};

function Harness() {
  const { activeCount, initialized, byWorkspace } = useBackgroundOperations();
  return <span>{initialized ? `${activeCount}:${byWorkspace("content_studio").length}` : "loading"}</span>;
}

afterEach(() => vi.restoreAllMocks());

describe("Background Operations observer", () => {
  it("uses one provider poll to expose active operations by workspace", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: String(input).includes("status=active") ? [running] : [],
    }), { status: 200 })));
    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><Harness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(screen.getByText("1:1")).toBeInTheDocument());
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });
});
