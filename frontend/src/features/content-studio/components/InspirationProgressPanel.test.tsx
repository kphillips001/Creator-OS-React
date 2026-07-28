import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ContentStudioGeneration } from "../types/generation";
import {
  inspirationProgressStage,
} from "./GenerationWorkflowSections";
import { InspirationProgressPanel } from "./InspirationProgressPanel";

function generation(
  changes: Partial<ContentStudioGeneration>,
): ContentStudioGeneration {
  return {
    runId: "run-inspire",
    jobId: null,
    promptPlanId: null,
    status: "queued",
    message: "Preparing inspiration",
    provider: "seedream_5_0_pro",
    completedCount: 0,
    failedCount: 0,
    processedCount: 0,
    totalCount: 6,
    progress: 0,
    images: [],
    ...changes,
  };
}

describe("Inspiration Progress", () => {
  it("renders completed, active, and upcoming autonomous stages", () => {
    render(<InspirationProgressPanel activeStage={2} />);

    const region = screen.getByRole("region", { name: "Inspiration Progress" });
    expect(region).toHaveTextContent("✓Understanding Ava");
    expect(region).toHaveTextContent("✓Loading Creative Intelligence");
    expect(screen.getByText("Creating today's inspiration").closest("li"))
      .toHaveAttribute("aria-current", "step");
    expect(region).toHaveTextContent("Building production prompts");
    expect(region).toHaveTextContent("Generating images");
  });

  it("maps existing backend states to the real pipeline without new API state", () => {
    expect(inspirationProgressStage(null, true, "")).toBe(0);
    expect(inspirationProgressStage(null, false, "run-inspire")).toBe(1);
    expect(inspirationProgressStage(generation({
      status: "planning",
      message: "Creating autonomous inspiration",
    }), false, "run-inspire")).toBe(2);
    expect(inspirationProgressStage(generation({
      status: "planning",
      message: "Creating prompt plan",
    }), false, "run-inspire")).toBe(3);
    expect(inspirationProgressStage(generation({
      jobId: "job-inspire",
      message: "Queued Image 1",
    }), false, "run-inspire")).toBe(4);
    expect(inspirationProgressStage(generation({
      status: "running",
      message: "Generating image 1",
    }), false, "run-inspire")).toBe(4);
  });
});
