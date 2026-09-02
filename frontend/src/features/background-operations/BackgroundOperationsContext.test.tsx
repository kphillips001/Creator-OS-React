import { render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
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

function ChangeObserver({ onChange }: { onChange: () => void }) {
  const context = useBackgroundOperations();
  useEffect(onChange, [context, onChange]);
  return null;
}

afterEach(() => vi.restoreAllMocks());

describe("Background Operations observer", () => {
  it("uses one provider poll to expose active operations by workspace", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: String(input).includes("status=active") ? [running] : [],
    }), { status: 200 })));
    render(<BackgroundOperationsProvider pollMilliseconds={60_000}><Harness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(screen.getByText("1:1")).toBeInTheDocument());
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/background-operations\/operation-1$/),
      expect.objectContaining({ headers: undefined }),
    );
  });

  it("backs idle polling off to fifteen seconds", async () => {
    const timer = vi.spyOn(window, "setTimeout");
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: [],
    }), { status: 200 })));
    render(<BackgroundOperationsProvider><Harness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(screen.getByText("0:0")).toBeInTheDocument());
    expect(timer.mock.calls.some(([, delay]) => delay === 15_000)).toBe(true);
  });

  it("backs hidden-tab polling off to sixty seconds", async () => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    const timer = vi.spyOn(window, "setTimeout");
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      success: true, operations: [],
    }), { status: 200 })));
    render(<BackgroundOperationsProvider><Harness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(screen.getByText("0:0")).toBeInTheDocument());
    expect(timer.mock.calls.some(([, delay]) => delay === 60_000)).toBe(true);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  });

  it("conditionally hydrates unchanged rich operation detail", async () => {
    let detailCalls = 0;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/operation-1")) {
        detailCalls += 1;
        if ((init?.headers as Record<string, string> | undefined)?.["If-None-Match"] === '"revision-1"') {
          return Promise.resolve(new Response(null, { status: 304, headers: { ETag: '"revision-1"' } }));
        }
        return Promise.resolve(new Response(JSON.stringify({ success: true, operation: running }), {
          status: 200, headers: { ETag: '"revision-1"' },
        }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        success: true, operations: url.includes("status=active") ? [running] : [],
      }), { status: 200 }));
    });
    render(<BackgroundOperationsProvider pollMilliseconds={20}><Harness /></BackgroundOperationsProvider>);
    await waitFor(() => expect(detailCalls).toBeGreaterThanOrEqual(2));
    expect(request.mock.calls.some(([input, init]) => String(input).endsWith("/operation-1")
      && (init?.headers as Record<string, string> | undefined)?.["If-None-Match"] === '"revision-1"')).toBe(true);
    expect(screen.getByText("1:1")).toBeInTheDocument();
  });

  it("does not publish a new context value for semantically unchanged polls", async () => {
    const changed = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify(
      String(input).endsWith("/operation-1")
        ? { success: true, operation: { ...running, metadata: {} } }
        : { success: true, operations: String(input).includes("status=active") ? [{ ...running, metadata: {} }] : [] },
    ), { status: 200 })));
    render(<BackgroundOperationsProvider pollMilliseconds={20}><Harness /><ChangeObserver onChange={changed} /></BackgroundOperationsProvider>);
    await waitFor(() => expect(screen.getByText("1:1")).toBeInTheDocument());
    const afterHydration = changed.mock.calls.length;
    await new Promise((resolve) => window.setTimeout(resolve, 80));
    expect(changed).toHaveBeenCalledTimes(afterHydration);
  });
});
