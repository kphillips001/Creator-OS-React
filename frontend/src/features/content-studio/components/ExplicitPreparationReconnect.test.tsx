import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackgroundOperationsProvider, type BackgroundOperation } from "../../background-operations/BackgroundOperationsContext";
import { ExplicitContentSection } from "./ExplicitContentSection";

const context = {
  status: "ready" as const,
  creatorProfileExists: true,
  activeReference: { assetId: 42, lastUsedAt: null },
};

function NavigationHarness() {
  const [visible, setVisible] = useState(true);
  return <>
    <button onClick={() => setVisible((current) => !current)} type="button">
      {visible ? "Navigate away" : "Return to Content Studio"}
    </button>
    {visible ? <ExplicitContentSection context={context} /> : <div>Another route</div>}
  </>;
}

afterEach(() => vi.restoreAllMocks());

describe("Explicit preparation reconnection", () => {
  it("does not present a rejected batch start as active 0/N generation", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.includes("/background-operations?status=")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true, operations: [] }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
        defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/inspire")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, hardcore: ["hardcore scene"], softcore: ["softcore scene"],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/batches") && options?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ success: true, operationId: "rejected-batch" }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/content-studio/explicit/batches/rejected-batch/start")) {
        return Promise.resolve(new Response(JSON.stringify({
          success: false, error: "Explicit batch cannot be started from its current state.",
        }), { headers: { "content-type": "application/json" }, status: 409 }));
      }
      if (url.endsWith("/content-studio/explicit/batches/rejected-batch/progress")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><ExplicitContentSection context={context} /></BackgroundOperationsProvider>);
    fireEvent.click(document.querySelector(".explicit-content-accordion > summary") as HTMLElement);
    const explicit = screen.getByRole("region", { name: "Explicit Content" });
    fireEvent.click(within(explicit).getByRole("button", { name: "Inspire Me" }));
    await within(explicit).findByText("hardcore scene");
    fireEvent.click(within(explicit).getByText(/Select All \(0 selected\)/));
    fireEvent.click(within(explicit).getByRole("button", { name: /Enhance & Generate \(2\)/ }));

    expect(await within(explicit).findByText("Explicit batch cannot be started from its current state.")).toBeInTheDocument();
    expect(within(explicit).queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls.some(([url]) => String(url).endsWith("/creative-tags/enhance"))).toBe(false);
  });

  it("does not resurrect handed-off concepts whose linked batch already succeeded", async () => {
    const inspiration: BackgroundOperation = {
      operationId: "old-inspiration", operationType: "content_studio_explicit_inspiration",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "SUCCEEDED", progressCurrent: 2, progressTotal: 2, progressPercent: 100,
      currentStage: "COMPLETE", stageMessage: "Handed off", createdAt: "2026-08-08T12:00:00Z",
      startedAt: "2026-08-08T12:00:00Z", completedAt: "2026-08-08T12:01:00Z",
      resultLocation: "/studio/content", resultReference: "completed-batch",
      errorCode: null, errorMessage: null, cancellationSupported: false,
      metadata: { phase: "HANDED_OFF", hardcore: ["stale hardcore"], softcore: ["stale softcore"] },
    };
    const batch: BackgroundOperation = {
      ...inspiration, operationId: "completed-batch", operationType: "content_studio_explicit_batch",
      resultReference: null, metadata: { phase: "complete", completedIdeas: 2, failedIdeas: 0 },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/background-operations?status=active")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true, operations: [] }), { status: 200 }));
      }
      if (url.includes("/background-operations?status=recent")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true, operations: [batch, inspiration] }), { status: 200 }));
      }
      if (url.endsWith("/content-studio/configuration")) {
        return Promise.resolve(new Response(JSON.stringify({
          success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
          providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
          defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
        }), { status: 200 }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><ExplicitContentSection context={context} /></BackgroundOperationsProvider>);

    expect(await screen.findByRole("button", { name: "Inspire Me" })).toBeInTheDocument();
    expect(screen.queryByText("stale hardcore")).not.toBeInTheDocument();
    expect(screen.queryByText("stale softcore")).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls.some(([url]) => String(url).endsWith("/explicit/inspire/old-inspiration"))).toBe(false);
  });

  it("durably dismisses a handed-off concept workspace without deleting its history", async () => {
    let dismissed = false;
    const operation: BackgroundOperation = {
      operationId: "handed-off-inspiration-1", operationType: "content_studio_explicit_inspiration",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "SUCCEEDED", progressCurrent: 2, progressTotal: 2, progressPercent: 100,
      currentStage: "COMPLETE", stageMessage: "Explicit concepts handed off to generation.",
      createdAt: "2026-08-09T12:00:00Z", startedAt: "2026-08-09T12:00:01Z", completedAt: "2026-08-09T12:01:00Z",
      resultLocation: "/studio/content", resultReference: "batch-1", errorCode: null, errorMessage: null,
      cancellationSupported: false,
      metadata: { phase: "HANDED_OFF", tierMode: "both", requestedCount: 2,
        hardcore: ["retained hardcore concept"], softcore: ["retained softcore concept"] },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      const current = { ...operation, metadata: { ...operation.metadata, workspaceDismissed: dismissed } };
      if (url.includes("/background-operations?status=active")) return Promise.resolve(new Response(JSON.stringify({ success: true, operations: [] }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=recent")) return Promise.resolve(new Response(JSON.stringify({ success: true, operations: [current] }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith(`/background-operations/${operation.operationId}`)) return Promise.resolve(new Response(JSON.stringify({ success: true, operation: current }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith(`/content-studio/explicit/inspire/${operation.operationId}/dismiss`) && options?.method === "POST") {
        dismissed = true;
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: current }), { headers: { "content-type": "application/json" }, status: 200 }));
      }
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }], defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><NavigationHarness /></BackgroundOperationsProvider>);
    expect(await screen.findByText("retained hardcore concept")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start Over" }));
    await waitFor(() => expect(screen.queryByText("retained hardcore concept")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Inspire Me" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Navigate away" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Content Studio" }));
    expect(screen.queryByText("retained hardcore concept")).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith(`/${operation.operationId}/dismiss`))).toHaveLength(1);
    expect(fetchSpy.mock.calls.some(([url]) => String(url).includes("/background-operations?status=recent"))).toBe(true);
  });

  it("reconnects durable concept generation and restores configuration and results without resubmitting", async () => {
    let active = false;
    let operation: BackgroundOperation = {
      operationId: "explicit-inspiration-1", operationType: "content_studio_explicit_inspiration",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "QUEUED", progressCurrent: 0, progressTotal: 2, progressPercent: 0,
      currentStage: "QUEUED", stageMessage: "Generating 5 ideas — 3 Softcore + 2 Hardcore…",
      createdAt: "2026-08-09T12:00:00Z", startedAt: null, completedAt: null,
      resultLocation: "/studio/content", resultReference: null, errorCode: null, errorMessage: null,
      cancellationSupported: true,
      metadata: { phase: "QUEUED", tierMode: "both", requestedCount: 5, softcoreCount: 3, hardcoreCount: 2, hardcore: [], softcore: [], concepts: [] },
    };
    let submissions = 0;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.endsWith(`/background-operations/${operation.operationId}`)) return Promise.resolve(new Response(JSON.stringify({
        success: true, operation,
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: url.includes("status=active") && active ? [operation] : [],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }], defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/inspire") && options?.method === "POST") {
        submissions += 1; active = true;
        return Promise.resolve(new Response(JSON.stringify({ success: true, error: null, operationId: operation.operationId, reused: false }), { headers: { "content-type": "application/json" }, status: 200 }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={10}><NavigationHarness /></BackgroundOperationsProvider>);
    fireEvent.click((await screen.findByText("🔞 Explicit Content")).closest("summary") as HTMLElement);
    const explicit = screen.getByRole("region", { name: "Explicit Content" });
    fireEvent.change(within(explicit).getByLabelText("Number of Ideas"), { target: { value: "5" } });
    fireEvent.click(within(explicit).getByRole("button", { name: "Inspire Me" }));
    expect(await within(explicit).findByText("Generating 5 ideas — 3 Softcore + 2 Hardcore…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Navigate away" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Content Studio" }));
    const restoredRunning = await screen.findByRole("region", { name: "Explicit Content" });
    expect(within(restoredRunning).getByLabelText("Number of Ideas")).toHaveValue("5");
    expect(within(restoredRunning).getByRole("button", { name: "Both" })).toHaveAttribute("aria-pressed", "true");
    expect(submissions).toBe(1);

    operation = { ...operation, status: "WAITING_EXTERNAL", currentStage: "WAITING_SELECTION", progressCurrent: 2, progressPercent: 100,
      stageMessage: "Explicit concepts are ready for selection.", metadata: { ...operation.metadata, phase: "WAITING_SELECTION",
        hardcore: ["hardcore one", "hardcore two"], softcore: ["softcore one", "softcore two", "softcore three"],
        concepts: [
          { id: "hardcore-0", tier: "hardcore", concept: "hardcore one", ordinal: 0 },
          { id: "hardcore-1", tier: "hardcore", concept: "hardcore two", ordinal: 1 },
          { id: "softcore-0", tier: "softcore", concept: "softcore one", ordinal: 2 },
          { id: "softcore-1", tier: "softcore", concept: "softcore two", ordinal: 3 },
          { id: "softcore-2", tier: "softcore", concept: "softcore three", ordinal: 4 },
        ] } };
    expect(await within(restoredRunning).findByText("softcore three")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Navigate away" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Content Studio" }));
    const restoredResults = await screen.findByRole("region", { name: "Explicit Content" });
    expect(await within(restoredResults).findByText("hardcore one")).toBeInTheDocument();
    expect(within(restoredResults).getByText("softcore three")).toBeInTheDocument();
    expect(submissions).toBe(1);
    expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith("/content-studio/explicit/inspire"))).toHaveLength(1);
  });

  it("restores 0-of-10 preparation without resubmitting or contacting the provider", async () => {
    let active = false;
    const enhanceNeverCompletes = new Promise<Response>(() => undefined);
    const operation = {
      operationId: "explicit-batch-1", operationType: "content_studio_explicit_batch",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "RUNNING", progressCurrent: 0, progressTotal: 10, progressPercent: 0,
      currentStage: "PREPARING", stageMessage: "Preparing idea 1 of 10...",
      createdAt: "2026-08-07T12:00:00Z", startedAt: "2026-08-07T12:00:00Z", completedAt: null,
      resultLocation: "/studio/content", resultReference: null, errorCode: null, errorMessage: null,
      cancellationSupported: false,
      metadata: {
        completedIdeas: 0, currentIdeaIndex: 1, failedIdeas: 0, phase: "preparing", totalIdeas: 10,
        prompts: [],
        items: Array.from({ length: 10 }, (_, ordinal) => ({
          error: "", id: `explicit-hardcore-${ordinal}`, imageUrl: "", jobId: null, ordinal,
          status: ordinal === 0 ? "enhancing" : "pending",
        })),
      },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.endsWith(`/background-operations/${operation.operationId}`)) return Promise.resolve(new Response(JSON.stringify({
        success: true, operation,
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=")) {
        const operations = url.includes("status=active") && active ? [operation] : [];
        return Promise.resolve(new Response(JSON.stringify({ success: true, operations }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
        defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/inspire")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null,
        hardcore: Array.from({ length: 5 }, (_, index) => `hardcore scene ${index + 1}`),
        softcore: Array.from({ length: 5 }, (_, index) => `softcore scene ${index + 1}`),
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/batches")) {
        active = true;
        return Promise.resolve(new Response(JSON.stringify({ success: true, operationId: operation.operationId }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.includes("/content-studio/explicit/batches/") && url.endsWith("/start")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.includes("/content-studio/explicit/batches/") && url.endsWith("/progress")) {
        return Promise.resolve(new Response(JSON.stringify({ success: true }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/content-studio/creative-tags/enhance") && options?.method === "POST") {
        return enhanceNeverCompletes;
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={10}><NavigationHarness /></BackgroundOperationsProvider>);
    const summary = await screen.findByText("🔞 Explicit Content");
    fireEvent.click(summary.closest("summary") as HTMLElement);
    const explicit = screen.getByRole("region", { name: "Explicit Content" });
    fireEvent.click(within(explicit).getByRole("button", { name: "Inspire Me" }));
    await within(explicit).findByText("hardcore scene 1");
    fireEvent.click(within(explicit).getByText(/Select All \(0 selected\)/));
    fireEvent.click(within(explicit).getByRole("button", { name: /Enhance & Generate \(10\)/ }));
    await within(explicit).findByText("Preparing idea 1 of 10...");
    expect(within(explicit).getByRole("button", { name: "Start Over" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Navigate away" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Content Studio" }));

    const restored = await screen.findByRole("region", { name: "Explicit Content" });
    expect(restored.closest("details")).toHaveAttribute("open");
    const live = await within(restored).findByRole("region", { name: "Live Generation" });
    expect(live).toHaveTextContent("0 of 10 Processed");
    expect(live).toHaveTextContent("Preparing idea 1 of 10...");
    expect(live).toHaveTextContent("Provider: Not contacted");
    await waitFor(() => expect(fetchSpy.mock.calls.some(([url]) => String(url).includes("status=active"))).toBe(true));
    expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith("/content-studio/explicit/batches"))).toHaveLength(1);
    expect(fetchSpy.mock.calls.some(([url]) => String(url).endsWith("/content-studio/generations"))).toBe(false);
  });

  it("confirms stop, preserves completed progress, and durably resets a cancelled workspace", async () => {
    let status: BackgroundOperation["status"] = "RUNNING";
    let workspaceDismissed = false;
    const operation = (): BackgroundOperation => ({
      operationId: "explicit-batch-stop-1", operationType: "content_studio_explicit_batch",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status, progressCurrent: 7, progressTotal: 12, progressPercent: 58.33,
      currentStage: status === "RUNNING" ? "GENERATING" : "CANCELLED",
      stageMessage: status === "RUNNING" ? "Generating idea 8 of 12..." : "Generation stopped by operator.",
      createdAt: "2026-08-14T20:25:51Z", startedAt: "2026-08-14T20:25:52Z",
      completedAt: status === "CANCELLED" ? "2026-08-14T20:40:00Z" : null,
      resultLocation: "/studio/content", resultReference: null, errorCode: null, errorMessage: null,
      cancellationSupported: true,
      metadata: { workspaceDismissed, completedIdeas: 7, totalIdeas: 12, phase: "generating", items: [] },
    });
    vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.includes("/background-operations?status=active")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: status === "RUNNING" ? [operation()] : [],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=recent")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: status === "CANCELLED" ? [operation()] : [],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/background-operations/explicit-batch-stop-1") && !options?.method) {
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: operation() }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/background-operations/explicit-batch-stop-1/cancel") && options?.method === "POST") {
        status = "CANCELLED";
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: operation() }), { headers: { "content-type": "application/json" }, status: 200 }));
      }
      if (url.endsWith("/content-studio/explicit/batches/explicit-batch-stop-1/reset") && options?.method === "POST") {
        workspaceDismissed = true;
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: operation() }), { headers: { "content-type": "application/json" }, status: 200 }));
      }
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
        defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><NavigationHarness /></BackgroundOperationsProvider>);
    const stopButton = await screen.findByRole("button", { name: "Stop Generation" });
    expect(stopButton.closest('[aria-label="Live Generation"]')).not.toBeNull();
    fireEvent.click(stopButton);
    expect(screen.getByRole("dialog", { name: "Stop this generation?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep Generating" }));
    expect(screen.queryByRole("dialog", { name: "Stop this generation?" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Stop Generation" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Stop this generation?" })).getByRole("button", { name: "Stop Generation" }));
    expect(await screen.findByText("Completed images were kept. Remaining images will not be generated.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset Studio" }));
    await waitFor(() => expect(screen.queryByText("Generation stopped.")).not.toBeInTheDocument());
    expect(workspaceDismissed).toBe(true);
    expect(screen.getByRole("button", { name: "Inspire Me" })).toBeInTheDocument();
  });

  it("rehydrates a partial batch and queues an idempotent failed-only retry", async () => {
    let retryQueued = false;
    const partial: BackgroundOperation = {
      operationId: "explicit-partial-1", operationType: "content_studio_explicit_batch",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "PARTIAL", progressCurrent: 2, progressTotal: 3, progressPercent: 100,
      currentStage: "COMPLETE", stageMessage: "2 completed · 1 failed",
      createdAt: "2026-08-18T12:00:00Z", startedAt: "2026-08-18T12:00:01Z", completedAt: "2026-08-18T12:02:00Z",
      resultLocation: "/studio/content", resultReference: null, errorCode: null, errorMessage: null,
      cancellationSupported: true,
      metadata: {
        completedIdeas: 2, failedIdeas: 1, currentIdeaIndex: 3, totalIdeas: 3, phase: "complete", prompts: [],
        items: [
          { id: "one", ordinal: 0, status: "completed", imageUrl: "/one", jobId: "one-job", error: "" },
          { id: "two", ordinal: 1, status: "failed", imageUrl: "", jobId: "two-job", error: "old failure" },
          { id: "three", ordinal: 2, status: "completed", imageUrl: "/three", jobId: "three-job", error: "" },
        ],
      },
    };
    const queued = { ...partial, status: "QUEUED" as const, completedAt: null, currentStage: "RETRY_QUEUED",
      stageMessage: "Retrying 1 failed items...", metadata: { ...partial.metadata, phase: "preparing" } };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.includes("/background-operations?status=active")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: retryQueued ? [queued] : [],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=recent")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: retryQueued ? [] : [partial],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/background-operations/explicit-partial-1")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operation: retryQueued ? queued : partial,
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/explicit/batches/explicit-partial-1/retry-failed") && options?.method === "POST") {
        retryQueued = true;
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: queued, reused: false }), {
          headers: { "content-type": "application/json" }, status: 200,
        }));
      }
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
        defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><ExplicitContentSection context={context} /></BackgroundOperationsProvider>);
    expect(await screen.findByText("2 completed · 1 failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Failed" }));
    await waitFor(() => expect(retryQueued).toBe(true));
    expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith("/retry-failed"))).toHaveLength(1);
  });

  it("hides another partial batch retry action while an authorized retry is active", async () => {
    const active: BackgroundOperation = {
      operationId: "active-retry", operationType: "content_studio_explicit_batch",
      originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "2",
      status: "RUNNING", progressCurrent: 5, progressTotal: 12, progressPercent: 41.67,
      currentStage: "RETRYING_FAILED", stageMessage: "Retrying failed item 2...",
      createdAt: "2026-08-18T12:01:00Z", startedAt: "2026-08-18T12:03:00Z", completedAt: null,
      resultLocation: "/studio/content", resultReference: null, errorCode: null, errorMessage: null,
      cancellationSupported: true,
      metadata: {
        completedIdeas: 5, failedIdeas: 0, retryingIdeas: 7, phase: "generating", items: [],
        retryCycle: { cycleId: "active-retry:retry:1", status: "ACTIVE" },
      },
    };
    const otherPartial: BackgroundOperation = {
      ...active,
      operationId: "other-partial", status: "PARTIAL", progressCurrent: 12,
      progressPercent: 100, currentStage: "COMPLETE", stageMessage: "4 completed · 8 failed",
      startedAt: "2026-08-18T11:00:00Z", completedAt: "2026-08-18T11:10:00Z",
      metadata: { completedIdeas: 4, failedIdeas: 8, phase: "complete", items: [] },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/background-operations?status=active")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: [active],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.includes("/background-operations?status=recent")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: [otherPartial],
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/background-operations/active-retry")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operation: active,
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/background-operations/other-partial")) return Promise.resolve(new Response(JSON.stringify({
        success: true, operation: otherPartial,
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      if (url.endsWith("/content-studio/configuration")) return Promise.resolve(new Response(JSON.stringify({
        success: true, error: null, modes: [], promptCount: { minimum: 1, maximum: 20, default: 5 },
        providers: [{ value: "seedream_5_0_pro", label: "Seedream" }],
        defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
      }), { headers: { "content-type": "application/json" }, status: 200 }));
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><ExplicitContentSection context={context} /></BackgroundOperationsProvider>);
    expect(await screen.findByRole("region", { name: "Live Generation" })).toBeInTheDocument();
    expect(screen.queryByText("4 completed · 8 failed")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry Failed" })).not.toBeInTheDocument();
  });
});
