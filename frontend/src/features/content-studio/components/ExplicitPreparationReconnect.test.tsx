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
});
