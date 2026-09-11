import type { ReactElement } from "react";
import { fireEvent, render as renderLibrary, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OfferingSellingControls } from "./OfferingSellingControls";

function LocationProbe() { const location = useLocation(); return <output data-testid="location">{location.pathname}</output>; }
const render = (ui: ReactElement) => renderLibrary(<MemoryRouter>{ui}<LocationProbe /></MemoryRouter>);

const offering = {
  offeringId: "offer-1", title: "Private Kitchen Set", description: "Five-image set",
  priceMinor: 1499, currency: "USD", primarySalesChannel: "AI_CHAT", status: "READY",
  publicationStatus: "LIVE", providerResourceStatus: "PRESENT",
  deliveryUrl: "https://example.invalid/delivery", lastError: null,
};
const json = (body: unknown, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);

afterEach(() => vi.unstubAllGlobals());

describe("OfferingSellingControls", () => {
  it("shows operator-friendly canonical readiness and keeps diagnostics contextual", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(offering)));
    render(<OfferingSellingControls offeringId="offer-1" />);
    expect(await screen.findByText("Live · Ready to Sell")).toBeInTheDocument();
    expect(screen.getByText("Private Kitchen Set")).toBeInTheDocument();
    expect(screen.getByText("$14.99")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    const catalog = screen.getByRole("link", { name: "Open Offering Catalog" });
    expect(catalog).toHaveAttribute("href", "/commerce");
    fireEvent.click(catalog);
    expect(screen.getByTestId("location")).toHaveTextContent("/commerce");
  });

  it("updates offering metadata through the canonical Commerce endpoint", async () => {
    const fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PATCH") return json({ ...offering, title: "New customer title", description: "Updated", priceMinor: 1799 });
      return json(offering);
    });
    vi.stubGlobal("fetch", fetch);
    render(<OfferingSellingControls offeringId="offer-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Offering Title" }), { target: { value: "New customer title" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Offering Description" }), { target: { value: "Updated" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Offering Price" }), { target: { value: "17.99" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Selling Details" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/commerce-authoring/offer-1", expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ title: "New customer title", description: "Updated", priceMinor: 1799, currency: "USD" }),
    })));
  });

  it("uses canonical publish and archive actions without duplicating publication logic", async () => {
    const ready = { ...offering, publicationStatus: "READY_TO_PUBLISH", providerResourceStatus: "UNVERIFIED" };
    const fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === "POST" ? json({ status: "accepted" }) : json(ready));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<OfferingSellingControls offeringId="offer-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Publish" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/commerce-authoring/offer-1/publish", expect.objectContaining({ method: "POST" })));
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/commerce-authoring/offer-1/archive", expect.objectContaining({ method: "POST" })));
  });
});
