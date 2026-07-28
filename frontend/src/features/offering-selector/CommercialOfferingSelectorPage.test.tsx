import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommercialOfferingSelectorPage } from "./CommercialOfferingSelectorPage";

const response = {
  items: [{
    buyer: {
      externalFanvueBuyerUuid: "buyer-1", telegramUserId: 22,
      displayName: "Buyer", handle: "buyer",
    },
    selectedOffering: {
      offeringId: "offering-1", title: "Private Release",
      publicationId: "publication-1", publicationProvider: "FANVUE",
      deliveryUrl: "https://share.fanvue.com/release",
      offeringType: "SINGLE_IMAGE", primarySalesChannel: "AI_CHAT",
    },
    selectionReason: "MOST_RECENT",
    exclusionReasons: ["PUBLICATION_NOT_LIVE"],
    evaluations: [{
      offeringId: "offering-1", title: "Private Release", eligible: true,
      exclusionReasons: [], publicationId: "publication-1",
      publicationProvider: "FANVUE", publicationStatus: "LIVE",
      deliveryUrlAvailable: true, offeringStatus: "READY",
      offeringType: "SINGLE_IMAGE", primarySalesChannel: "AI_CHAT",
      publishedAt: "2026-07-26T00:00:00Z",
    }, {
      offeringId: "offering-2", title: "Draft Release", eligible: false,
      exclusionReasons: ["PUBLICATION_NOT_LIVE"], publicationId: null,
      publicationProvider: null, publicationStatus: "DRAFT",
      deliveryUrlAvailable: false, offeringStatus: "READY",
      offeringType: "SINGLE_IMAGE", primarySalesChannel: "AI_CHAT",
      publishedAt: null,
    }],
    selectorMetadata: {
      candidateCount: 2, eligibleCount: 1, rejectedCount: 1,
      featuredSupported: false,
    },
  }],
  total: 1, page: 1, pageSize: 20, totalPages: 1,
};

afterEach(() => vi.restoreAllMocks());

describe("CommercialOfferingSelectorPage", () => {
  it("shows selected offering, eligibility matrix, and diagnostics", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => response,
    }));
    render(<CommercialOfferingSelectorPage />);
    expect(await screen.findByText("Private Release")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {
      name: "View selector buyer-1",
    }));
    expect(screen.getByRole("heading", {
      name: "Eligibility Matrix",
    })).toBeInTheDocument();
    expect(screen.getByText("Draft Release")).toBeInTheDocument();
    expect(screen.getAllByText("Publication Not Live")).toHaveLength(2);
    fireEvent.click(screen.getByText("Expandable diagnostics"));
    expect(screen.getByText(/"candidateCount": 2/)).toBeInTheDocument();
  });

  it("sends search without exposing editing controls", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true, json: async () => response,
    });
    vi.stubGlobal("fetch", fetch);
    render(<CommercialOfferingSelectorPage />);
    await screen.findByText("Private Release");
    fireEvent.change(screen.getByLabelText(
      "Search Commercial Offering Selector",
    ), { target: { value: "buyer" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(fetch).toHaveBeenLastCalledWith(
      expect.stringContaining("search=buyer"), expect.anything(),
    ));
    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
  });
});
