import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { BackgroundOperationsProvider } from "../background-operations/BackgroundOperationsContext";
import { RegenerationStudioPage } from "./RegenerationStudioPage";

const response = (body: unknown, status = 200) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);
const source = { success: true, eligibility: { canRegenerate: true }, source: { generatedImageId: "source-1", mediaUrl: "/source.png", providerDisplayName: "Seedream", modelDisplayName: "Seedream 5", sourceWorkflow: "premium", creativeMode: "premium_teaser" } };
const workspace = { success: true, operation: { status: "SUCCEEDED", progressCurrent: 1, progressTotal: 1, progressPercent: 100, currentStage: "COMPLETE", stageMessage: "Complete", errorMessage: null, metadata: { completedCount: 1, failedCount: 0 } }, run: { operationId: "op-1", sourceGeneratedImageId: "source-1", requestedCount: 1, status: "SUCCEEDED" }, results: [{ resultId: "result-1", variationIndex: 1, status: "SUCCEEDED", generatedImageId: "regen-1", generationRecipeId: "recipe-1", disposition: "PENDING_REVIEW", mediaUrl: "/result.png", errorCode: null, errorMessage: null }] };

afterEach(() => vi.restoreAllMocks());
function CurrentLocation() { return <output data-testid="current-location">{useLocation().search}</output>; }
const renderPage = (path: string) => render(<MemoryRouter initialEntries={[path]}><BackgroundOperationsProvider pollMilliseconds={60000}><CurrentLocation /><Routes><Route path="/studio/regeneration" element={<RegenerationStudioPage />} /><Route path="/library/generations" element={<div>Library destination</div>} /></Routes></BackgroundOperationsProvider></MemoryRouter>);

describe("Regeneration Studio", () => {
  it("shows the direct-navigation empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("workspace/current")
      ? response({ success: true, workspace: null }) : response({ success: true, operations: [] }));
    renderPage("/studio/regeneration");
    expect(screen.getByText("Restoring Regeneration Studio…")).toBeInTheDocument();
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Generation Library/ })).toBeInTheDocument();
  });

  it("discovers and restores the canonical workspace from the plain route", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("workspace/current")) return response({ success: true, workspace: { operationId: "op-1", sourceGeneratedImageId: "source-1" } });
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.endsWith("/regeneration/op-1")) return response(workspace);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration");
    expect(await screen.findByRole("img", { name: "Regeneration source" })).toHaveAttribute("src", "/source.png");
    expect(screen.getByRole("img", { name: "Regenerated variation 1" })).toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent("operation=op-1");
  });

  it("loads a source, defaults to one, and submits only source and count", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.endsWith("/api/v1/regeneration") && init?.method === "POST") return response({ success: true, operationId: "op-1" }, 202);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1")) return response(workspace);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1");
    expect(await screen.findByRole("img", { name: "Regeneration source" })).toHaveAttribute("src", "/source.png");
    expect(screen.getByLabelText("Number of variations")).toHaveValue("1");
    fireEvent.change(screen.getByLabelText("Number of variations"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration", expect.objectContaining({ method: "POST", body: JSON.stringify({ source_generated_image_id: "source-1", count: 5 }) })));
  });

  it("promotes selected results and resets after backend finalizes unselected results", async () => {
    const second = { ...workspace.results[0], resultId: "result-2", variationIndex: 2, generatedImageId: "regen-2" };
    const partialWorkspace = { ...workspace, run: { ...workspace.run, requestedCount: 2 }, results: [workspace.results[0], second] };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/promote")) return response({ success: true, message: "1 image added to Generation Library", workspaceDismissed: true });
      if (url.endsWith("/regeneration/op-1")) return response(partialWorkspace);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    const image = await screen.findByRole("img", { name: "Regenerated variation 1" });
    fireEvent.click(image);
    expect(screen.getByRole("dialog", { name: "Regeneration image preview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    fireEvent.click(screen.getAllByRole("checkbox", { name: "Select" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: /Send Selected/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration/op-1/promote", expect.objectContaining({ body: JSON.stringify({ result_ids: ["result-1"] }) })));
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("current-location")).toBeEmptyDOMElement());
  });

  it("auto-resets through the canonical reset path after all pending results are promoted", async () => {
    let promoted = false;
    const second = { ...workspace.results[0], resultId: "result-2", variationIndex: 2, generatedImageId: "regen-2" };
    const before = { ...workspace, run: { ...workspace.run, requestedCount: 2 }, results: [workspace.results[0], second] };
    const after = { ...before, results: before.results.map((item) => ({ ...item, disposition: "PROMOTED" })) };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/promote")) { promoted = true; return response({ success: true, workspaceDismissed: true }); }
      if (url.endsWith("/regeneration/op-1")) return response(promoted ? after : before);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    const checks = await screen.findAllByRole("checkbox", { name: "Select" });
    checks.forEach((check) => fireEvent.click(check));
    fireEvent.click(screen.getByRole("button", { name: /Send Selected/ }));
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("current-location")).toBeEmptyDOMElement());
  });

  it("cleans a stale operation URL when the backend reports a dismissed workspace", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1")) return response({ success: false, code: "WORKSPACE_DISMISSED", error: "finalized" }, 410);
      if (url.includes("workspace/current")) return response({ success: true, workspace: null });
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("current-location")).toBeEmptyDOMElement());
  });

  it("does not reset when promotion fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/promote")) return response({ success: false, error: "Promotion failed." }, 409);
      if (url.endsWith("/regeneration/op-1")) return response(workspace);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: /Send Selected/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Promotion failed.");
    expect(screen.getByRole("img", { name: "Regenerated variation 1" })).toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent("source=source-1");
  });

  it("ignores failed and archived variations when deciding to auto-reset", async () => {
    let promoted = false;
    const second = { ...workspace.results[0], resultId: "result-2", variationIndex: 2, generatedImageId: "regen-2" };
    const failed = { ...workspace.results[0], resultId: "failed", variationIndex: 3, status: "FAILED", disposition: "PENDING_REVIEW", mediaUrl: null };
    const archived = { ...workspace.results[0], resultId: "archived", variationIndex: 4, disposition: "ARCHIVED" };
    const before = { ...workspace, run: { ...workspace.run, requestedCount: 4 }, results: [workspace.results[0], second, failed, archived] };
    const after = { ...before, results: [{ ...workspace.results[0], disposition: "PROMOTED" }, { ...second, disposition: "PROMOTED" }, failed, archived] };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/promote")) { promoted = true; return response({ success: true }); }
      if (url.endsWith("/regeneration/op-1")) return response(promoted ? after : before);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    const checks = await screen.findAllByRole("checkbox", { name: "Select" });
    checks.forEach((check) => fireEvent.click(check));
    fireEvent.click(screen.getByRole("button", { name: /Send Selected/ }));
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
  });

  it("archives selected pending results without deleting their workspace", async () => {
    let archived = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/archive")) { archived = true; return response({ success: true, message: "1 regenerated image archived" }); }
      if (url.endsWith("/regeneration/op-1")) return response(archived ? { ...workspace, results: [{ ...workspace.results[0], disposition: "ARCHIVED" }] } : workspace);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: /Archive Selected/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration/op-1/archive", expect.objectContaining({ body: JSON.stringify({ result_ids: ["result-1"] }) })));
    expect(await screen.findByText("1 regenerated image archived")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("img", { name: "Regenerated variation 1" })).not.toBeInTheDocument());
  });

  it("requires archive before resetting unresolved results", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1/archive")) return response({ success: true });
      if (url.endsWith("/regeneration/op-1/dismiss")) return response({ success: true });
      if (url.endsWith("/regeneration/op-1")) return response(workspace);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    await screen.findByRole("img", { name: "Regenerated variation 1" });
    fireEvent.click(screen.getByRole("button", { name: "Reset Studio" }));
    expect(screen.getByRole("dialog", { name: "Archive unresolved results?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("img", { name: "Regenerated variation 1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset Studio" }));
    fireEvent.click(screen.getByRole("button", { name: /Archive & Reset/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration/op-1/archive", expect.objectContaining({ body: JSON.stringify({ result_ids: ["result-1"] }) })));
    expect(await screen.findByText("Choose a Regenerate-eligible image")).toBeInTheDocument();
  });

  it("disables reset while regeneration is active", async () => {
    const running = { ...workspace, operation: { ...workspace.operation, status: "RUNNING", progressPercent: 40 } };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/regeneration/source/")) return response(source);
      if (url.includes("/background-operations")) return response({ success: true, operations: [] });
      if (url.endsWith("/regeneration/op-1")) return response(running);
      return response({ success: false }, 500);
    });
    renderPage("/studio/regeneration?source=source-1&operation=op-1");
    expect(await screen.findByRole("button", { name: "Reset Studio" })).toBeDisabled();
  });
});
