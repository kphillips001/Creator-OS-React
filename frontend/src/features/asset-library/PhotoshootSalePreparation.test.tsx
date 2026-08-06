import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PrepareForSaleDialog, SessionSellingPanel } from "./PhotoshootSalePreparation";

const response = (body: unknown, ok = true) => Promise.resolve({
  ok, status: ok ? 200 : 409, json: () => Promise.resolve(body),
} as Response);

const readiness = {
  deliverableId: "deliverable-1", photoshootSessionId: "session-1", strategyVersion: "v1",
  status: "READY", statusLabel: "Ready for Session Selling", paidStepCount: 1,
  readyPaidStepCount: 1, teaserReady: true, steps: [
    { assetId: 1, shotOrder: 1, position: 1, role: "FREE_TEASER", access: "FREE", ready: true, deliveryMethod: "Direct Telegram delivery", imageUrl: "/shot-1" },
    { assetId: 2, shotOrder: 2, position: 2, role: "FIRST_UNLOCK", access: "PAID", ready: true,
      publicationStatus: "LIVE", providerResourceStatus: "PRESENT", deliveryUrl: "https://fanvue.example/link-2",
      priceMinor: 500, currency: "USD", publishedAt: "2026-08-05T10:00:00Z" },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe("SessionSellingPanel", () => {
  it("keeps persisted URLs hidden until View Published Assets is opened", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(readiness));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByText("Ready for Session Selling")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open Shot 2 link" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View Published Assets" }));
    expect(screen.getByText("Direct Telegram delivery")).toBeInTheDocument();
    expect(screen.getByText("USD 5.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Shot 2 link" })).toHaveAttribute("href", "https://fanvue.example/link-2");
    expect(screen.getByRole("button", { name: "Copy Shot 2 link" })).toBeInTheDocument();
  });

  it.each([
    ["READY", "Ready for Session Selling"],
    ["NEEDS_ATTENTION", "Needs Attention"],
  ] as const)("polls only readiness until preparation becomes %s", async (status, statusLabel) => {
    const preparing = { ...readiness, status: "PREPARING", statusLabel: "Preparing", readyPaidStepCount: 0,
      steps: readiness.steps.map((step) => step.access === "PAID" ? { ...step, ready: false, publicationStatus: "PUBLISHING" } : step) };
    const settled = { ...preparing, status, statusLabel,
      readyPaidStepCount: status === "READY" ? 1 : 0,
      steps: preparing.steps.map((step) => step.access === "PAID" ? {
        ...step, ready: status === "READY", publicationStatus: status === "READY" ? "LIVE" : "FAILED",
        error: status === "NEEDS_ATTENTION" ? "Provider rejected upload." : null,
      } : step) };
    let calls = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(calls++ === 0 ? preparing : settled));
    const onReadinessChange = vi.fn();
    vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
      queueMicrotask(() => { if (typeof handler === "function") handler(); });
      return 1;
    }) as typeof window.setInterval);
    vi.spyOn(window, "clearInterval").mockImplementation(() => undefined);
    render(<SessionSellingPanel deliverableId="deliverable-1" onReadinessChange={onReadinessChange} />);
    expect(await screen.findByRole("heading", { name: statusLabel })).toBeInTheDocument();
    expect(onReadinessChange).toHaveBeenLastCalledWith(settled);
    expect(fetch.mock.calls.every(([input]) => String(input) === "/api/v1/assets/photoshoots/deliverable-1/sale-preparation")).toBe(true);
    if (status === "READY") expect(screen.getByText("Paid steps: 1 of 1 ready")).toBeInTheDocument();
    else {
      expect(screen.getByText("Provider rejected upload.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Retry Failed Preparation" })).toBeInTheDocument();
    }
  });

  it("opens ordered pricing review and submits the complete strategy snapshot once", async () => {
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared", paidStepCount: 2, readyPaidStepCount: 0,
      steps: [readiness.steps[0], { ...readiness.steps[1], ready: false, priceMinor: null, deliveryUrl: null, imageUrl: "/shot-2" },
        { assetId: 3, shotOrder: 3, position: 3, role: "ESCALATION", access: "PAID", ready: false, priceMinor: 900, currency: "USD", imageUrl: "/shot-3" }] };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(options?.method === "POST" ? { ...unprepared, status: "PREPARING", statusLabel: "Preparing" } : unprepared));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare for Sale" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByText(/Shot [123]/).map((node) => node.textContent)).toEqual(["Shot 1", "Shot 2", "Shot 3"]);
    expect(within(dialog).getByText("Direct Telegram delivery")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Shot 1 price")).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Shot 3 price")).toHaveValue(9);
    expect(within(dialog).getByRole("button", { name: "Prepare Photoshoot" })).toBeDisabled();
    fireEvent.change(await screen.findByLabelText("Shot 2 price"), { target: { value: "5.00" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Prepare Photoshoot" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/sale-preparation",
      expect.objectContaining({ method: "POST" }),
    ));
    const post = fetch.mock.calls.find(([, options]) => options?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ strategyVersion: "v1", steps: [
      { assetId: 1, shotOrder: 1, salesPosition: 1, role: "FREE_TEASER", access: "FREE", currency: "USD" },
      { assetId: 2, shotOrder: 2, salesPosition: 2, role: "FIRST_UNLOCK", access: "PAID", priceMinor: 500, currency: "USD" },
      { assetId: 3, shotOrder: 3, salesPosition: 3, role: "ESCALATION", access: "PAID", priceMinor: 900, currency: "USD" },
    ] });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Preparing Photoshoot...")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Photoshoot preparation progress" })).toBeInTheDocument();
    expect(screen.getByText("Waiting to prepare FIRST UNLOCK")).toBeInTheDocument();
  });

  it("blocks blank, nonnumeric, below-minimum, and above-maximum paid prices", async () => {
    const unprepared = { ...readiness, status: "NOT_PREPARED", steps: readiness.steps.map((step) => step.access === "PAID" ? { ...step, priceMinor: null } : step) };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(unprepared));
    render(<PrepareForSaleDialog deliverableId="deliverable-1" onClose={() => undefined} />);
    const input = await screen.findByLabelText("Shot 2 price");
    const button = screen.getByRole("button", { name: "Prepare Photoshoot" });
    expect(button).toBeDisabled();
    for (const value of ["abc", "2.99", "500.01", "5.001"]) {
      fireEvent.change(input, { target: { value } });
      expect(button).toBeDisabled();
    }
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("prepopulates and locks an existing live publication price", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ ...readiness, steps: readiness.steps.map((step) => step.access === "PAID" ? { ...step, priceLocked: true } : step) }));
    render(<PrepareForSaleDialog deliverableId="deliverable-1" onClose={() => undefined} />);
    expect(await screen.findByLabelText("Shot 2 price")).toBeDisabled();
    expect(screen.getByText(/does not currently support editing/)).toBeInTheDocument();
  });
});
