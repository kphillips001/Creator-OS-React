import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FanvueWebhookMonitorPage } from "./FanvueWebhookMonitorPage";
import type { FanvueWebhookMonitorItem } from "./types";

function item(
  overrides: Partial<FanvueWebhookMonitorItem> = {},
): FanvueWebhookMonitorItem {
  return {
    monitorId: "monitor-1",
    timestamp: "2026-07-24T20:00:00Z",
    requestPath: "/webhooks/fanvue",
    payloadSize: 120,
    payload: {
      buyer: { uuid: "buyer-1" },
      transactionOrderId: "transaction-1",
      mediaUuid: "media-1",
    },
    rawJson: "{\"transactionOrderId\":\"transaction-1\"}",
    headers: { "content-type": "application/json" },
    signatureHeaders: { "x-fanvue-signature": "signature" },
    eventName: "purchase.created",
    eventId: "event-1",
    httpStatus: 200,
    signatureValid: true,
    processingResult: { success: true },
    normalizationResult: { event_type: "purchase_created" },
    persistenceResult: { persisted: true },
    deliveryMetadata: { received: true },
    exception: null,
    durationMs: 15,
    retryCount: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FanvueWebhookMonitorPage", () => {
  it("renders newest-first rows, searches and filters, and opens JSON details", async () => {
    const older = item({
      monitorId: "older",
      timestamp: "2026-07-24T19:00:00Z",
      eventName: "message.received",
      eventId: "message-1",
      payload: { sender: { uuid: "buyer-2" } },
    });
    const newest = item({ monitorId: "newest" });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        items: [older, newest],
        lastWebhookReceived: newest.timestamp,
        storage: "process-memory",
        limit: 100,
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    render(<FanvueWebhookMonitorPage />);

    await screen.findByText("purchase.created");
    expect(screen.getByText("purchase.created").closest("tr")?.previousElementSibling)
      .toBeNull();
    expect(screen.getByText("No webhook selected.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search webhooks"), {
      target: { value: "buyer-2" },
    });
    expect(screen.queryByText("purchase.created")).not.toBeInTheDocument();
    expect(screen.getByText("message.received")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search webhooks"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Webhook filter"), {
      target: { value: "purchase" },
    });
    expect(screen.getByText("purchase.created")).toBeInTheDocument();
    expect(screen.queryByText("message.received")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", {
      name: `View ${newest.eventName} webhook ${newest.eventId}`,
    }));
    expect(screen.queryByText("No webhook selected.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Selected webhook details")).toBeInTheDocument();
    expect(screen.getByText("Pretty JSON")).toBeInTheDocument();
    expect(screen.getByText("Headers")).toBeInTheDocument();
    expect(screen.getByText("Signature headers")).toBeInTheDocument();
    expect(screen.getByText("Delivery metadata")).toBeInTheDocument();
    expect(screen.getByText("Processing metadata")).toBeInTheDocument();
    expect(screen.getByText("Normalization result")).toBeInTheDocument();
    expect(screen.getByText("Persistence result")).toBeInTheDocument();
    expect(screen.getByText("Exception")).toBeInTheDocument();
    expect(screen.getByText("Retry count")).toBeInTheDocument();
    expect(screen.getByText("transactionOrderId")).toBeInTheDocument();
  });

  it("shows the no-webhook badge and waiting empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        items: [],
        lastWebhookReceived: null,
        storage: "process-memory",
        limit: 100,
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    render(<FanvueWebhookMonitorPage />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.getAllByText("No webhook received")).toHaveLength(2);
    expect(screen.getByText("Waiting for Fanvue webhook...")).toBeInTheDocument();
  });

  it("filters failures independently from successful requests", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        items: [
          item(),
          item({
            monitorId: "failed",
            eventName: "refund.failed",
            httpStatus: 401,
            exception: "invalid_signature",
          }),
        ],
        lastWebhookReceived: "2026-07-24T20:00:00Z",
        storage: "process-memory",
        limit: 100,
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    render(<FanvueWebhookMonitorPage />);
    await screen.findByText("refund.failed");
    fireEvent.change(screen.getByLabelText("Webhook filter"), {
      target: { value: "failed" },
    });
    expect(screen.getByText("refund.failed")).toBeInTheDocument();
    expect(screen.queryByText("purchase.created")).not.toBeInTheDocument();
  });
});
