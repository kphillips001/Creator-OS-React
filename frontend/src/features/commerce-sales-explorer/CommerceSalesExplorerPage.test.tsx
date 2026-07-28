import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommerceSalesExplorerPage } from "./CommerceSalesExplorerPage";

const item = {
  offeringId: "offer-1", title: "Beach Set", description: "Sunny collection",
  offeringType: "PHOTOSET", priceMinor: 999, currency: "USD",
  primarySalesChannel: "AI_CHAT", heroAssetId: 42,
  heroUrl: "/api/v1/assets/42/thumbnail",
  deliveryUrl: "https://fanvue.com/fvml-1", provider: "FANVUE",
  providerResourceId: "link-1", publishedAt: "2026-07-24T12:00:00Z",
  status: "FULFILLABLE",
};
const response = (items: unknown[], totalPages = 1) => Promise.resolve({
  ok: true,
  json: () => Promise.resolve({
    items, total: items.length, page: 1, pageSize: 20, totalPages,
  }),
} as Response);

afterEach(() => vi.unstubAllGlobals());

describe("CommerceSalesExplorerPage", () => {
  it("renders eligible offerings and opens read-only details", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response([item])));
    render(<CommerceSalesExplorerPage />);
    expect(await screen.findByText("Beach Set")).toBeInTheDocument();
    expect(screen.getByText("$9.99")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Media Link" })).toHaveAttribute("href", item.deliveryUrl);
    fireEvent.click(screen.getByRole("button", { name: "Open Beach Set" }));
    expect(screen.getByRole("dialog", { name: "Beach Set details" })).toHaveTextContent("link-1");
  });

  it("searches visible results", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response([item])));
    render(<CommerceSalesExplorerPage />);
    await screen.findByText("Beach Set");
    fireEvent.change(screen.getByRole("textbox", { name: "Search Commerce Sales" }), { target: { value: "missing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByText("No eligible offerings match this search.")).toBeInTheDocument();
  });

  it("renders the empty state and paginates through the API", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) => {
      void input;
      return response([], 2);
    });
    vi.stubGlobal("fetch", fetch);
    render(<CommerceSalesExplorerPage />);
    expect(await screen.findByText("No offerings are currently eligible for AI Chat.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(String(fetch.mock.calls.at(-1)?.[0])).toContain("page=2"));
  });
});
