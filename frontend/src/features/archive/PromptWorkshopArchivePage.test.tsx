import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PromptWorkshopArchivePage } from "./PromptWorkshopArchivePage";

const batches = [
  {
    batchId: "batch-newer",
    createdAt: "2026-07-17T14:00:00",
    lane: "explicit",
    prompts: ["newer prompt one", "newer prompt two"],
    requestText: "newer studio brief",
    usedPromptNumbers: [],
  },
  {
    batchId: "batch-older",
    createdAt: "2026-07-16T11:30:00",
    lane: "premium",
    prompts: ["archived prompt one", "archived prompt two"],
    requestText: "archived hotel brief",
    usedPromptNumbers: [2],
  },
];

describe("PromptWorkshopArchivePage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/content-studio/prompt-workshop/archive") && !init?.method) {
        return new Response(JSON.stringify({ success: true, error: null, batches }), {
          headers: { "content-type": "application/json" },
        });
      }
      if (url.includes("/content-studio/prompt-workshop/archive/") && init?.method === "POST") {
        return new Response(JSON.stringify({ success: true, error: null }), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ success: false, error: "Unexpected request" }), { status: 404 });
    }));
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("renders preserved batches and switches the prompt viewer", async () => {
    render(<MemoryRouter><PromptWorkshopArchivePage /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Prompt Workshop Archive" })).toBeInTheDocument();
    expect(await screen.findByText("newer prompt one")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Archived prompt batch"), { target: { value: "batch-older" } });
    expect(screen.getByText("archived hotel brief")).toBeInTheDocument();
    expect(screen.getByText("archived prompt two").closest("li")).toHaveTextContent("used archived prompt two");
  });

  it("keeps the existing archive retrieval and usage APIs", async () => {
    render(<MemoryRouter initialEntries={["/system/archive/prompts"]}><Routes><Route path="/system/archive/prompts" element={<PromptWorkshopArchivePage />} /><Route path="/studio/content" element={<div>Content Studio destination</div>} /></Routes></MemoryRouter>);
    await screen.findByText("newer prompt one");
    fireEvent.change(screen.getByLabelText("Archived prompt number"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Use Archived" }));

    await waitFor(() => expect(screen.getByText("Content Studio destination")).toBeInTheDocument());
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.some(([url]) => String(url).endsWith("/content-studio/prompt-workshop/archive"))).toBe(true);
    const usage = calls.find(([url]) => String(url).includes("/prompt-workshop/archive/batch-newer/use"));
    expect(JSON.parse(String(usage?.[1]?.body))).toEqual({ promptNumber: 2 });
  });
});
