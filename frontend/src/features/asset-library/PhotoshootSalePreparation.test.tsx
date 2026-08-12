import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    expect(await screen.findByRole("heading", { name: "READY" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open Shot 2 link" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View Published Assets" }));
    expect(screen.getByText("Direct Telegram delivery")).toBeInTheDocument();
    expect(screen.getByText("USD 5.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Shot 2 link" })).toHaveAttribute("href", "https://fanvue.example/link-2");
    expect(screen.getByRole("button", { name: "Copy Shot 2 link" })).toBeInTheDocument();
  });

  it.each([
    ["READY", "READY"],
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
    if (status === "READY") expect(screen.getByText("1 of 1 paid images ready")).toBeInTheDocument();
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
    expect(await screen.findByRole("heading", { name: "Preparing..." })).toBeInTheDocument();
    expect(screen.getByText("Preparing paid images: 0 of 1")).toBeInTheDocument();
    poll?.();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "Preparing..." })).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: "Set Session Prices" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Prepare Session" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByRole("heading", { name: "Preparing..." })).toBeInTheDocument();
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
    expect(screen.getByText("Paid images ready: 1 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View Published Assets" }));
    expect(screen.getByRole("link", { name: "Open Shot 3 link" })).toHaveAttribute("href", "https://fanvue.example/live-3");
  });

  it("opens ordered pricing review and submits the complete strategy snapshot once", async () => {
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared", paidStepCount: 2, readyPaidStepCount: 0,
      steps: [readiness.steps[0], { ...readiness.steps[1], ready: false, priceMinor: null, deliveryUrl: null, imageUrl: "/shot-2" },
        { assetId: 3, shotOrder: 3, position: 3, role: "ESCALATION", access: "PAID", ready: false, priceMinor: 900, currency: "USD", imageUrl: "/shot-3" }] };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(options?.method === "POST" ? { ...unprepared, status: "PREPARING", statusLabel: "Preparing" } : unprepared));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Pricing Required" })).toBeInTheDocument();
    expect(screen.getByText("2 paid images need prices before this Session can be prepared.")).toBeInTheDocument();
    expect(screen.queryByText(/Paid steps:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare Session" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set Session Prices" }));
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

  it("automatically starts durable strategy preparation without a manual generation action", async () => {
    const missing = { ...readiness, strategyVersion: "", strategyExists: false,
      strategyStatus: "MISSING", status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared",
      paidStepCount: 0, readyPaidStepCount: 0, teaserReady: false, steps: [] };
    const queued = { ...missing, strategyOperation: { operationId: "operation-1", status: "QUEUED" } };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => response(options?.method === "POST" ? queued : missing));
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(screen.getByRole("heading", { name: "Loading…" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Preparing Strategy..." })).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    expect(screen.getByText("Analyzing the completed Photoshoot for sequential selling.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Generate Session Strategy/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/session-sales-strategy",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("refreshes to price preparation after the durable strategy operation succeeds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const missing = { ...readiness, strategyVersion: "", strategyExists: false,
      strategyStatus: "MISSING", status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared",
      paidStepCount: 0, readyPaidStepCount: 0, teaserReady: false, steps: [] };
    const queued = { ...missing, strategyOperation: { operationId: "operation-1", status: "RUNNING" } };
    const unprepared = { ...readiness, status: "NOT_PREPARED", statusLabel: "Not Prepared",
      readyPaidStepCount: 0, steps: readiness.steps.map((step) => step.access === "PAID"
        ? { ...step, ready: false, priceMinor: null, deliveryUrl: null } : step) };
    let getCount = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => {
      if (options?.method === "POST") return response(queued);
      getCount += 1;
      if (getCount === 1) return response(missing);
      return response(unprepared);
    });
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Preparing Strategy..." })).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(await screen.findByRole("heading", { name: "Pricing Required" })).toBeInTheDocument();
    expect(screen.getByText("1 paid image needs a price before this Session can be prepared.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set Session Prices" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/session-sales-strategy",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("reconnects to a durable failed strategy operation and offers retry", async () => {
    const failed = { ...readiness, strategyVersion: "", strategyExists: false,
      strategyStatus: "MISSING", status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared",
      paidStepCount: 0, readyPaidStepCount: 0, teaserReady: false, steps: [],
      strategyOperation: { operationId: "operation-1", status: "FAILED", errorMessage: "Grok response was invalid." } };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).endsWith("/retry")) return response({ success: true });
      return response(failed);
    });
    render(<SessionSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Strategy Needs Attention" })).toBeInTheDocument();
    expect(screen.getByText("Grok response was invalid.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Generate Session Strategy/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/background-operations/operation-1/retry", { cache: "no-store", method: "POST" },
    ));
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
  const teaser = (status: "NOT_CONFIGURED" | "READY" = "NOT_CONFIGURED") => ({
    status, statusLabel: status === "READY" ? "Promotional Teaser Ready" : "Teaser Not Configured",
    commercialRole: "BUNDLE_PROMOTIONAL_TEASER", sourceAssetId: status === "READY" ? 1 : null,
    teaserAssetId: status === "READY" ? 100 : null, blurStrength: 24,
    maskWidth: status === "READY" ? 100 : null, maskHeight: status === "READY" ? 100 : null,
    maskVersion: "selective_blur_mask_v1", maskUrl: status === "READY" ? "/mask" : null,
    previewUrl: status === "READY" ? "/preview" : null, error: null,
    candidates: [{ assetId: 1, shotOrder: 1, imageUrl: "/image-1" }],
  });
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

  it("authors five Bundle captions while the promotional teaser is not configured", async () => {
    const options = Array.from({ length: 5 }, (_, index) => ({ text: `Complete 3-photo set option ${index + 1} 🔥` }));
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      String(input).endsWith("/captions/generate") ? response({ captions: options }) : response(bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", imageCount: 3, priceMinor: 1499,
      deliveryUrl: "https://fanvue.example/existing-link",
      promotionalTeaser: { status: "NOT_CONFIGURED", statusLabel: "Teaser Not Configured", candidates: [] },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false,
        readinessError: "Create a promotional teaser before publishing." },
    })));
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    const button = await screen.findByRole("button", { name: "Generate Captions with AI" });
    expect(button).toBeEnabled();
    expect(screen.queryByText("A READY promotional teaser is required before authoring captions.")).not.toBeInTheDocument();
    expect(screen.getByText("Create a promotional teaser before publishing.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Choose Bundle Content Vault Caption" })).not.toBeInTheDocument();
    fireEvent.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Choose Bundle Content Vault Caption" });
    expect(within(dialog).getAllByRole("button").filter((item) => item.textContent?.includes("Complete 3-photo set"))).toHaveLength(5);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/content-vault/captions/generate",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeDisabled();
  });

  it("restores a persisted teaser and caption when the Bundle inspector reopens", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 1499,
      offeringId: "offering-1", publicationId: "fanvue-publication-1",
      deliveryUrl: "https://fanvue.example/existing-link", promotionalTeaser: teaser("READY"),
      contentVaultCaption: { text: "The complete set is waiting for you 🔥", source: "GROK" },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true, readinessError: null },
    })));
    const view = render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    expect(await screen.findByRole("button", { name: "Edit Caption" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Generate Captions with AI" })).toBeEnabled();
    expect(screen.getByText("The complete set is waiting for you 🔥")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
    view.unmount();
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    expect(await screen.findByRole("button", { name: "Edit Caption" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
  });

  it("enables captions immediately after recovering a missing teaser without preparing paid media", async () => {
    const missing = bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 1499,
      offeringId: "offering-1", publicationId: "fanvue-publication-1",
      deliveryUrl: "https://fanvue.example/existing-link", promotionalTeaser: teaser(),
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false,
        readinessError: "Create a promotional teaser before publishing." },
    });
    const recovered = { ...missing, promotionalTeaser: teaser("READY"),
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false,
        readinessError: "Select and save a Content Vault caption before publishing." } };
    const context = { clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([255, 255, 255, 255]) })),
      globalCompositeOperation: "source-over", fillStyle: "#fff" };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,bWFzaw==");
    let teaserSaved = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      if (init?.method === "PUT") { teaserSaved = true; return response(teaser("READY")); }
      return response(teaserSaved ? recovered : missing);
    });
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    expect(await screen.findByRole("button", { name: "Generate Captions with AI" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(
      { left: 0, top: 0, width: 100, height: 100 } as DOMRect,
    );
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.click(screen.getByRole("button", { name: "Save Teaser" }));
    expect(await screen.findByRole("button", { name: "Generate Captions with AI" })).toBeEnabled();
    expect(screen.getByText("Promotional Teaser Ready")).toBeInTheDocument();
    expect(screen.getByText("Fanvue Media Link ready · USD 14.99")).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "PUT")).toHaveLength(1);
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("opens the chooser only after five captions arrive and persists the selection", async () => {
    const options = Array.from({ length: 5 }, (_, index) => ({ text: `The full set is waiting ${index + 1} 🔥` }));
    const selectedText = "The full set is waiting 2 🔥";
    const prepared = bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 3000,
      promotionalTeaser: { status: "READY", statusLabel: "Ready", candidates: [] },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false,
        readinessError: "Select and save a Content Vault caption before publishing." },
    });
    const selected = { ...prepared, contentVaultCaption: { text: selectedText, source: "GROK" },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true, readinessError: null } };
    let getCount = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/captions/generate")) return response({ captions: options });
      if (url.endsWith("/caption") && init?.method === "PUT") return response({ caption: { text: selectedText } });
      getCount += 1;
      return response(getCount === 1 ? prepared : selected);
    });
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    fireEvent.click(await screen.findByRole("button", { name: "Generate Captions with AI" }));
    expect(screen.queryByRole("dialog", { name: "Choose Bundle Content Vault Caption" })).not.toBeInTheDocument();
    const dialog = await screen.findByRole("dialog", { name: "Choose Bundle Content Vault Caption" });
    expect(within(dialog).getAllByRole("button").filter((item) => item.textContent?.includes("full set"))).toHaveLength(5);
    expect(within(dialog).getByRole("button", { name: "Write My Own" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Use Caption" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: selectedText }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Use Caption" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/content-vault/caption",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ text: selectedText, source: "GROK" }) }),
    ));
    expect(await screen.findByText(selectedText)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
  });

  it("persists a direct operator caption through the canonical endpoint without generating captions", async () => {
    const prepared = bundle({ status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 1499,
      promotionalTeaser: teaser("READY"), contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false } });
    const saved = { ...prepared, contentVaultCaption: { text: "My own Bundle caption", source: "MANUAL" },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true } };
    let getCount = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/caption") && init?.method === "PUT") return response({ caption: { text: "My own Bundle caption" } });
      getCount += 1;
      return response(getCount === 1 ? prepared : saved);
    });
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    expect(await screen.findByRole("button", { name: "Write Your Own Caption" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Write Your Own Caption" }));
    const textarea = screen.getByRole("textbox", { name: "Content Wall caption" });
    expect(screen.getByRole("button", { name: "Save Caption" })).toBeDisabled();
    fireEvent.change(textarea, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Save Caption" })).toBeDisabled();
    fireEvent.change(textarea, { target: { value: "  My own Bundle caption  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save Caption" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/deliverable-1/content-vault/caption",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ text: "My own Bundle caption", source: "MANUAL" }) }),
    ));
    expect(await screen.findByText("My own Bundle caption")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/captions/generate"))).toBe(false);
  });

  it("edits a persisted Bundle caption without invoking Grok and refreshes readiness", async () => {
    const prepared = bundle({ status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 1499,
      promotionalTeaser: teaser("READY"), contentVaultCaption: { text: "Original wording", source: "GROK" },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true } });
    const saved = { ...prepared, contentVaultCaption: { text: "Operator revision", source: "MANUAL" } };
    let savedCaption = false;
    let getCount = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/caption") && init?.method === "PUT") { savedCaption = true; return response({ caption: saved.contentVaultCaption }); }
      getCount += 1;
      return response(savedCaption ? saved : prepared);
    });
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Caption" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Content Wall caption" }), { target: { value: "Operator revision" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Caption" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/content-vault/caption"),
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ text: "Operator revision", source: "MANUAL" }) })));
    await waitFor(() => expect(getCount).toBeGreaterThan(1));
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/captions/generate"))).toBe(false);
  });

  it.each([
    ["request failure", { detail: "Grok caption generation failed." }, false, "Grok caption generation failed."],
    ["zero candidates", { captions: [] }, true, "Caption generation did not return five usable options. Please retry."],
  ])("keeps the chooser closed on %s", async (_label, body, ok, message) => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).endsWith("/captions/generate")
      ? response(body, ok) : response(bundle({
        status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 3000,
        promotionalTeaser: { status: "READY", statusLabel: "Ready", candidates: [] },
      })));
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    fireEvent.click(await screen.findByRole("button", { name: "Generate Captions with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByRole("dialog", { name: "Choose Bundle Content Vault Caption" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Captions with AI" })).toBeEnabled();
  });

  it("refreshes authoritative readiness after a rejected retry", async () => {
    const needsAttention = bundle({
      status: "NEEDS_ATTENTION", statusLabel: "Paid Bundle Needs Attention", priceMinor: 3000,
      error: "Old provider error.", promotionalTeaser: { status: "NOT_CONFIGURED", statusLabel: "Teaser Not Configured", candidates: [] },
    });
    const ready = bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 3000,
      error: null, deliveryUrl: "https://fanvue.example/bundle",
      promotionalTeaser: { status: "NOT_CONFIGURED", statusLabel: "Teaser Not Configured", candidates: [] },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: false, readinessError: "Create a promotional teaser before publishing." },
    });
    let gets = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => {
      if (options?.method === "POST") return Promise.resolve(response({ detail: "Conflict" }, false));
      gets += 1;
      return Promise.resolve(response(gets === 1 ? needsAttention : ready));
    });
    render(<BundleSellingPanel deliverableId="deliverable-1" salesChannel="CONTENT_WALL" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry Bundle Preparation" }));
    expect(await screen.findByRole("heading", { name: "Paid Bundle Ready" })).toBeInTheDocument();
    expect(screen.queryByText("Old provider error.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry Bundle Preparation" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Fanvue Media Link/ })).toBeInTheDocument();
    expect(screen.getByText("Teaser Not Configured")).toBeInTheDocument();
    expect(screen.getByText("Create a promotional teaser before publishing.")).toBeInTheDocument();
  });

  it("recovers stale needs-attention readiness when the panel remounts", async () => {
    const needsAttention = bundle({
      status: "NEEDS_ATTENTION", statusLabel: "Paid Bundle Needs Attention", priceMinor: 3000,
      error: "Old provider error.",
    });
    const ready = bundle({
      status: "READY", statusLabel: "Paid Bundle Ready", priceMinor: 3000,
      error: null, deliveryUrl: "https://fanvue.example/bundle",
    });
    let gets = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response(gets++ === 0 ? needsAttention : ready)));
    const view = render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("button", { name: "Retry Bundle Preparation" })).toBeInTheDocument();
    view.unmount();
    render(<BundleSellingPanel deliverableId="deliverable-1" />);
    expect(await screen.findByRole("heading", { name: "Paid Bundle Ready" })).toBeInTheDocument();
    expect(screen.queryByText("Old provider error.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry Bundle Preparation" })).not.toBeInTheDocument();
  });
});
