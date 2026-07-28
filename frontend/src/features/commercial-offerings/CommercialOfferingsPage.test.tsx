import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommercialOfferingsPage } from "./CommercialOfferingsPage";

const offering = {
  offeringId: "offer-1", offeringType: "PHOTOSET", title: "Beach Day",
  description: "A sunny collection.", heroAssetId: 42, heroUrl: "/thumb/42",
  primarySalesChannel: "AI_CHAT", status: "DRAFT", assetCount: 2, assets: [],
  createdAt: "2026-07-23T00:00:00Z", updatedAt: "2026-07-23T00:00:00Z",
};
const response = (body: unknown, ok = true) => Promise.resolve({
  ok, json: () => Promise.resolve(body),
} as Response);
const fulfillment = {
  offeringId: "offer-1", title: "Beach Day", description: "A sunny collection.",
  offeringType: "PHOTOSET", primarySalesChannel: "AI_CHAT", priceMinor: 999,
  currency: "USD", heroAssetId: 42, orderedAssetIds: [42, 43],
  publicationId: "publication-1", provider: "FANVUE",
  providerResourceId: null, deliveryUrl: null, publicationStatus: "READY_TO_PUBLISH",
  providerResourceStatus: "UNVERIFIED", lastReconciledAt: null, publishedAt: null,
  fulfillable: false, ineligibilityReason: "PUBLICATION_NOT_LIVE",
  eligibleForAiChat: false, eligibleForTelegramWall: false,
};

afterEach(() => vi.unstubAllGlobals());

describe("CommercialOfferingsPage", () => {
  it("lists Commercial Offerings with required foundation fields", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({
      items: [offering], total: 1, page: 1, pageSize: 20, totalPages: 1,
    })));
    render(<MemoryRouter><CommercialOfferingsPage /></MemoryRouter>);
    expect(await screen.findByText("Beach Day")).toBeInTheDocument();
    expect(screen.getByText("Photoset", { selector: "small" })).toBeInTheDocument();
    expect(screen.getByText("Ai Chat")).toBeInTheDocument();
    expect(screen.getByText("A sunny collection.")).toBeInTheDocument();
  });

  it("creates an offering from selected Available Inventory assets", async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      if (init?.method === "POST") return response({ ...offering, assets: [
        { assetId: 42, position: 1, isHero: true },
        { assetId: 43, position: 2, isHero: false },
      ] });
      return response({ items: [], total: 0, page: 1, pageSize: 20, totalPages: 1 });
    });
    vi.stubGlobal("fetch", fetch);
    render(<MemoryRouter initialEntries={["/commerce/offerings?asset_ids=42,43"]}><CommercialOfferingsPage /></MemoryRouter>);
    expect(screen.getByRole("dialog", { name: "Create Offering" })).toHaveTextContent("2 Available Inventory assets selected.");
    fireEvent.change(screen.getByRole("combobox", { name: "Offering Type" }), { target: { value: "PHOTOSET" } });
    fireEvent.click(screen.getByRole("radio", { name: "AI Chat" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Offering title" }), { target: { value: "Beach Day" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Hero Asset" }), { target: { value: "43" } });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Create Offering" })).getByRole("button", { name: "Create Offering" }));

    await waitFor(() => {
      const call = fetch.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        offeringType: "PHOTOSET", title: "Beach Day", description: null,
        heroAssetId: 43, primarySalesChannel: "AI_CHAT", assetIds: [42, 43],
      });
    });
  });

  it("displays publication status and prevents duplicate provider creation", async () => {
    const publication = {
      publicationId: "publication-1", commercialOfferingId: "offer-1",
      provider: "FANVUE", status: "READY_TO_PUBLISH", externalProductId: null,
      publishedAt: null, createdAt: "2026-07-23T00:00:00Z",
      updatedAt: "2026-07-23T00:00:00Z", lastError: null, retryCount: 0,
      publicationMetadata: {}, providerResourceStatus: "UNVERIFIED",
      lastReconciledAt: null, reconciliationResult: null,
    };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/commercial-publications?")) return response({ items: [publication] });
      if (url.includes("/commercial-fulfillments/")) return response(fulfillment);
      if (url.endsWith("/commercial-offerings/offer-1")) return response(offering);
      return response({ items: [offering], total: 1, page: 1, pageSize: 20, totalPages: 1 });
    }));
    render(<MemoryRouter><CommercialOfferingsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "View Beach Day" }));
    const detail = await screen.findByLabelText("Beach Day details");
    expect(detail).toHaveTextContent("Commercial Publications");
    expect(detail).toHaveTextContent("Ready To Publish");
    expect(detail).toHaveTextContent("Not published");
    expect(detail).toHaveTextContent("Not assigned");
    expect(detail).toHaveTextContent("Offering unavailable");
    expect(screen.getByRole("button", { name: "Reconcile Provider" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Fanvue Publication Exists" })).toBeDisabled();
  });

  it("creates a Fanvue publication record without provider actions", async () => {
    const created = {
      publicationId: "publication-1", commercialOfferingId: "offer-1",
      provider: "FANVUE", status: "READY_TO_PUBLISH", externalProductId: null,
      publishedAt: null, createdAt: "2026-07-23T00:00:00Z",
      updatedAt: "2026-07-23T00:00:00Z", lastError: null, retryCount: 0,
      publicationMetadata: {}, providerResourceStatus: "UNVERIFIED",
      lastReconciledAt: null, reconciliationResult: null,
    };
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return response(created);
      if (url.includes("/commercial-publications?")) return response({ items: [] });
      if (url.includes("/commercial-fulfillments/")) return response(fulfillment);
      if (url.endsWith("/commercial-offerings/offer-1")) return response(offering);
      return response({ items: [offering], total: 1, page: 1, pageSize: 20, totalPages: 1 });
    });
    vi.stubGlobal("fetch", fetch);
    render(<MemoryRouter><CommercialOfferingsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "View Beach Day" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create Publication" }));
    const dialog = screen.getByRole("dialog", { name: "Create Publication" });
    expect(dialog).toHaveTextContent("does not contact Fanvue or publish anything");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create Publication Record" }));
    await waitFor(() => {
      const call = fetch.mock.calls.find(([, init]) => init?.method === "POST");
      expect(String(call?.[0])).toBe("/api/v1/commercial-publications");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        commercialOfferingId: "offer-1", provider: "FANVUE",
      });
    });
    expect(await screen.findByText("Ready To Publish")).toBeInTheDocument();
  });
});
