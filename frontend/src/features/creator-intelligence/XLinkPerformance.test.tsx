import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { XLinkPerformance } from "./XLinkPerformance";
import { clearOverviewQueryCache } from "./overviewQueryCache";

const report = {
  period: { key: "TODAY", timezone: "America/New_York", start: "2026-09-08T04:00:00Z", end: "2026-09-09T04:00:00Z", generatedAt: "2026-09-08T12:00:00Z", interval: "[start,end)" },
  historicalBoundary: "Tracking begins with attributed Creator-OS X publications.",
  items: [
    { primaryPostId: "post-1", ctaPostId: "cta-1", accountName: "AvaBlackthorne", caption: "A tracked post", thumbnailUrl: "/media/1", publishedAt: "2026-09-08T14:35:00Z", trackingState: "TRACKED", linkClicks: 23 },
    { primaryPostId: "post-2", ctaPostId: null, accountName: "AvaBlackthorne", caption: "An older post", thumbnailUrl: "/media/2", publishedAt: "2026-09-08T13:00:00Z", trackingState: "TRACKING_UNAVAILABLE", linkClicks: null },
    { primaryPostId: "post-3", ctaPostId: null, accountName: "AvaBlackthorne", caption: "No CTA post", thumbnailUrl: "/media/3", publishedAt: "2026-09-08T12:00:00Z", trackingState: "NO_CTA", linkClicks: null },
    { primaryPostId: "post-4", ctaPostId: null, accountName: "AvaBlackthorne", caption: "Failed CTA post", thumbnailUrl: "/media/4", publishedAt: "2026-09-08T11:00:00Z", trackingState: "FAILED_CTA", linkClicks: null },
  ],
};
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => { vi.restoreAllMocks(); clearOverviewQueryCache(); });

describe("X Link Performance", () => {
  it("loads independently and distinguishes tracked clicks from unavailable tracking", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(report));
    render(<XLinkPerformance />);
    expect(await screen.findByText("23")).toBeInTheDocument();
    expect(screen.getByText("Tracking unavailable")).toBeInTheDocument();
    expect(screen.getByText("No CTA")).toBeInTheDocument();
    expect(screen.getByText("CTA failed")).toBeInTheDocument();
    expect(screen.getByText("A tracked post")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Published X post" })[0]).toHaveAttribute("src", "/media/1");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/creator-intelligence/x-link-performance?period=TODAY", expect.objectContaining({ cache: "no-store" }));
  });

  it("uses the shared period keys and contains API errors", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("LAST_7_DAYS") ? response(report) : response({ detail: "Analytics unavailable." }, 503));
    render(<XLinkPerformance />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Analytics unavailable.");
    fireEvent.click(screen.getByRole("button", { name: "7 Days" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/creator-intelligence/x-link-performance?period=LAST_7_DAYS", expect.anything()));
    expect(await screen.findByText("23")).toBeInTheDocument();
  });
});
