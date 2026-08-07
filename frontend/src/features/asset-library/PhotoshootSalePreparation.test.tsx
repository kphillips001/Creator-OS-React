import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BundleSellingPanel, PrepareForSaleDialog, SessionSellingPanel } from "./PhotoshootSalePreparation";

const response = (body: unknown, ok = true) => Promise.resolve({
  ok, status: ok ? 200 : 409, json: () => Promise.resolve(body),
} as Response);

const readiness = {
  deliverableId: "deliverable-1", photoshootSessionId: "session-1", strategyVersion: "v1",
  sellingMode: "SESSION" as const,
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

  it("keeps PREPARING visible while a polling refetch is pending", async () => {
    const preparing = { ...readiness, status: "PREPARING", statusLabel: "Preparing", readyPaidStepCount: 0,
      steps: readiness.steps.map((step) => step.access === "PAID" ? { ...step, ready: false, publicationStatus: "PUBLISHING" } : step) };
    let poll: (() => void) | undefined;
    let resolveRefresh: ((value: Response) => void) | undefined;
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response(preparing))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveRefresh = resolve; }));
    vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === "function") poll = () => handler();
      return 1;
    }) as typeof window.setInterval);
    vi.spyOn(window, "clearInterval").mockImplementation(() => undefined);

    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Preparing" })).toBeInTheDocument();
    poll?.();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "Preparing" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Loading…" })).not.toBeInTheDocument();
    resolveRefresh?.(await response(preparing));
  });

  it("closes the preparation dialog once and polling never reopens it", async () => {
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared",
      readyPaidStepCount: 0, steps: readiness.steps.map((step) => step.access === "PAID"
        ? { ...step, ready: false, deliveryUrl: null } : step) };
    const preparing = { ...unprepared, status: "PREPARING", statusLabel: "Preparing" };
    let calls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(
      options?.method === "POST" ? preparing : calls++ === 0 ? unprepared : preparing,
    ));
    vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
      queueMicrotask(() => { if (typeof handler === "function") handler(); });
      return 1;
    }) as typeof window.setInterval);
    vi.spyOn(window, "clearInterval").mockImplementation(() => undefined);

    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare Session" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Prepare Session" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByRole("heading", { name: "Preparing" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows concise timeout copy, identifies the step, and preserves partial links", async () => {
    const partial = { ...readiness, status: "NEEDS_ATTENTION", statusLabel: "Needs Attention",
      paidStepCount: 2, readyPaidStepCount: 1, steps: [readiness.steps[0], {
        ...readiness.steps[1], ready: false, publicationStatus: "FAILED", deliveryUrl: null,
        error: "HTTPSConnectionPool(host='api.fanvue.com'): Read timed out. (read timeout=30)",
      }, {
        ...readiness.steps[1], assetId: 3, shotOrder: 3, position: 3, role: "ESCALATION",
        ready: true, publicationStatus: "LIVE", deliveryUrl: "https://fanvue.example/live-3",
        error: null,
      }] };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(partial));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);

    expect(await screen.findByText("Fanvue timed out while preparing FIRST UNLOCK.")).toBeInTheDocument();
    expect(screen.getByText("Shot 2 · FIRST UNLOCK")).toBeInTheDocument();
    expect(screen.queryByText(/HTTPSConnectionPool/)).not.toBeInTheDocument();
    expect(screen.getByText("Paid steps: 1 of 2 ready")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View Published Assets" }));
    expect(screen.getByRole("link", { name: "Open Shot 3 link" })).toHaveAttribute("href", "https://fanvue.example/live-3");
  });

  it("opens ordered pricing review and submits the complete strategy snapshot once", async () => {
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared", paidStepCount: 2, readyPaidStepCount: 0,
      steps: [readiness.steps[0], { ...readiness.steps[1], ready: false, priceMinor: null, deliveryUrl: null, imageUrl: "/shot-2" },
        { assetId: 3, shotOrder: 3, position: 3, role: "ESCALATION", access: "PAID", ready: false, priceMinor: 900, currency: "USD", imageUrl: "/shot-3" }] };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(options?.method === "POST" ? { ...unprepared, status: "PREPARING", statusLabel: "Preparing" } : unprepared));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare Session" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByText(/Shot [123]/).map((node) => node.textContent)).toEqual(["Shot 1", "Shot 2", "Shot 3"]);
    expect(within(dialog).getByText("Direct Telegram delivery")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Shot 1 price")).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Shot 3 price")).toHaveValue(9);
    expect(within(dialog).getByRole("button", { name: "Prepare Session" })).toBeDisabled();
    fireEvent.change(await screen.findByLabelText("Shot 2 price"), { target: { value: "5.00" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Prepare Session" }));
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
    const button = screen.getByRole("button", { name: "Prepare Session" });
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

  it("shows a normal missing-strategy state only after loading finishes", async () => {
    const missing = { ...readiness, strategyVersion: "", strategyExists: false,
      strategyStatus: "MISSING", status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared",
      paidStepCount: 0, readyPaidStepCount: 0, teaserReady: false, steps: [] };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(missing));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(screen.getByRole("heading", { name: "Loading…" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Not Prepared" })).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    expect(screen.getByText("No Session Sales Strategy has been created yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Session Strategy" })).toBeInTheDocument();
  });

  it("generates explicitly, refetches readiness, and opens the existing price review", async () => {
    const missing = { ...readiness, strategyVersion: "", strategyExists: false,
      strategyStatus: "MISSING", status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared",
      paidStepCount: 0, readyPaidStepCount: 0, teaserReady: false, steps: [] };
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared",
      readyPaidStepCount: 0, steps: readiness.steps.map((step) => step.access === "PAID"
        ? { ...step, ready: false, priceMinor: null, deliveryUrl: null } : step) };
    let initial = true;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => {
      if (options?.method === "POST") return response(unprepared);
      if (initial) { initial = false; return response(missing); }
      return response(unprepared);
    });
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Generate Session Strategy" }));
    expect(screen.getByRole("button", { name: "Generating Session Strategy…" })).toBeDisabled();
    const dialog = await screen.findByRole("dialog");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/session-sales-strategy",
      expect.objectContaining({ method: "POST" }),
    );
    expect(within(dialog).queryByLabelText("Shot 1 price")).not.toBeInTheDocument();
    expect(await within(dialog).findByLabelText("Shot 2 price")).toBeInTheDocument();
  });

  it("replaces loading with an operator-facing API error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ detail: "Strategy service unavailable." }, false));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Session Selling Unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Strategy service unavailable.");
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });
});

describe("BundleSellingPanel", () => {
  const bundle = (changes: Record<string, unknown> = {}) => ({
    deliverableId: "deliverable-1", photoshootSessionId: "session-1", sellingMode: "BUNDLE",
    status: "NOT_CONFIGURED", statusLabel: "Paid Bundle Not Configured", imageCount: 5,
    priceMinor: null, currency: "USD", ...changes,
  });

  it("shows one price and submits only the Bundle price", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(
      options?.method === "POST" ? bundle({ status: "PREPARING", statusLabel: "Preparing Paid Bundle", priceMinor: 3000,
        autonomousSales: { status: "NEEDS_SETUP", statusLabel: "Needs Setup", reason: "Bundle media is still preparing" } }) : bundle(),
    ));
    render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByText("5 images")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Shot .* price/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Bundle Price"), { target: { value: "30.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Prepare Bundle" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/sale-preparation",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ priceMinor: 3000 }) }),
    ));
    expect(await screen.findByText("Preparing Bundle...")).toBeInTheDocument();
  });

  it.each([
    ["PREPARING", "Preparing Paid Bundle"],
    ["READY", "Paid Bundle Ready"],
    ["NEEDS_ATTENTION", "Paid Bundle Needs Attention"],
  ] as const)("renders persisted %s readiness", async (status, label) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(bundle({
      status, statusLabel: label, priceMinor: 3000,
      error: status === "NEEDS_ATTENTION" ? "Upload failed." : null,
      deliveryUrl: status === "READY" ? "https://fanvue.example/bundle" : null,
    })));
    render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: label })).toBeInTheDocument();
    if (status === "READY") expect(screen.getByRole("link", { name: /Open Fanvue Media Link/ })).toBeInTheDocument();
    if (status === "NEEDS_ATTENTION") expect(screen.getByRole("button", { name: "Retry Bundle Preparation" })).toBeInTheDocument();
  });

  it.each([
    ["NOT_CONFIGURED", "NOT_CONFIGURED", "Needs Bundle media"],
    ["READY", "NOT_CONFIGURED", "Needs promotional teaser"],
    ["NOT_CONFIGURED", "READY", "Needs Bundle media"],
  ] as const)("keeps autonomous sales blocked for paid=%s teaser=%s", async (paidStatus, teaserStatus, reason) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(bundle({
      status: paidStatus,
      statusLabel: paidStatus === "READY" ? "Paid Bundle Ready" : "Paid Bundle Not Configured",
      priceMinor: paidStatus === "READY" ? 3000 : null,
      deliveryUrl: paidStatus === "READY" ? "https://fanvue.example/bundle" : null,
      promotionalTeaser: { status: teaserStatus, statusLabel: teaserStatus === "READY" ? "Ready" : "Not Configured", candidates: [] },
      autonomousSales: { status: "NEEDS_SETUP", statusLabel: "Needs Setup", reason },
    })));
    render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByText("Autonomous Sales: Needs Setup")).toBeInTheDocument();
    expect(screen.getByText(reason)).toBeInTheDocument();
  });

  it("shows aggregate readiness only when paid media and the teaser are ready", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 3000,
      deliveryUrl: "https://fanvue.example/bundle",
      promotionalTeaser: { status: "READY", statusLabel: "Ready", candidates: [] },
      autonomousSales: { status: "READY", statusLabel: "Ready to Sell", reason: null },
    })));
    render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Paid Bundle Ready" })).toBeInTheDocument();
    expect(screen.getByText("Autonomous Sales: Ready to Sell")).toBeInTheDocument();
  });
});
