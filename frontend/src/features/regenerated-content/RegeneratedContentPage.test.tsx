import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RegeneratedContentPage } from "./RegeneratedContentPage";

const item = { resultId: "result-1", operationId: "op-1", variationIndex: 2, generatedImageId: "regen-1", sourceGeneratedImageId: "source-1", providerDisplayName: "Seedream", modelDisplayName: "5.0 Pro", sourceWorkflow: "premium", generatedAt: "2026-08-11T12:00:00Z", archivedAt: "2026-08-11T13:00:00Z", mediaUrl: "/archived.png" };
const response = (body: unknown) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);

afterEach(() => vi.restoreAllMocks());

describe("Regenerated Content Archive", () => {
  it("loads safe archive metadata and restores to the original workspace", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).includes("/archive/items")) return response({ success: true, items: [item], totalPages: 1 });
      if (String(input).endsWith("/restore") && init?.method === "POST") return response({ success: true, redirect: "/studio/regeneration?source=source-1&operation=op-1" });
      return response({ success: false });
    });
    render(<MemoryRouter initialEntries={["/system/archive/regenerated"]}><Routes><Route path="/system/archive/regenerated" element={<RegeneratedContentPage />} /><Route path="/studio/regeneration" element={<div>Restored workspace</div>} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("img", { name: "Archived variation 2" })).toHaveAttribute("src", "/archived.png");
    expect(screen.getByText(/Seedream/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Restore to Regeneration Studio/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration/op-1/results/result-1/restore", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByText("Restored workspace")).toBeInTheDocument();
  });

  it("promotes an archived result through the canonical promotion endpoint", async () => {
    let promoted = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).includes("/archive/items")) return response({ success: true, items: promoted ? [] : [item], totalPages: 1 });
      if (String(input).endsWith("/promote") && init?.method === "POST") { promoted = true; return response({ success: true }); }
      return response({ success: false });
    });
    render(<MemoryRouter><RegeneratedContentPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Send to Generation Library/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/regeneration/op-1/promote", expect.objectContaining({ body: JSON.stringify({ result_ids: ["result-1"] }) })));
    await waitFor(() => expect(screen.queryByRole("img", { name: "Archived variation 2" })).not.toBeInTheDocument());
  });
});
