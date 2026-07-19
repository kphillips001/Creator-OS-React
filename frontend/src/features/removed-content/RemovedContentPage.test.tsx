import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RemovedContentPage } from "./RemovedContentPage";

const item = { archiveId: "archive-1", generationLibraryId: "image-1", removedAt: "2026-07-18T12:00:00Z", provider: "flux", prompt: "Window light portrait", mediaUrl: "/removed.png" };
const jsonResponse = (body: unknown, status = 200) => Promise.resolve({ ok: status < 400, json: () => Promise.resolve(body) } as Response);

describe("RemovedContentPage", () => {
  it("searches, restores, and requires confirmation before permanent deletion", async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/removed/items")) return jsonResponse({ items: [item] });
      if (url.endsWith("/restore") && init?.method === "POST") return jsonResponse({ success: true });
      if (url.endsWith("/permanent-delete") && init?.method === "POST") return jsonResponse({ success: true });
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetch);
    const { unmount } = render(<RemovedContentPage />);
    expect(await screen.findByText("Window light portrait")).toBeInTheDocument();
    expect(screen.getByText("Window light portrait").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText("Window light portrait", { selector: ".removed-card__body > p" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search prompts, providers, or IDs"), { target: { value: "missing" } });
    expect(screen.getByText("No removed content matches these filters.")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search prompts, providers, or IDs"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Delete Permanently" }));
    expect(screen.getByRole("heading", { name: "Delete Permanently?" })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/permanent-delete"))).toBe(false);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete Permanently" })[1]!);
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/permanent-delete"))).toBe(true));
    expect(fetch.mock.calls.find(([url]) => String(url).endsWith("/permanent-delete"))?.[1]?.body).toBe('{"confirmed":true}');
    unmount();

    fetch.mockClear();
    render(<RemovedContentPage />);
    expect(await screen.findByText("Window light portrait")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/restore"))).toBe(true));
  });
});
