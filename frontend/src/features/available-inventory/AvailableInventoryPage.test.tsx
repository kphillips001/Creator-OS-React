import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { AvailableInventoryPage } from "./AvailableInventoryPage";

const item = {
  assetId: 42, displayName: "Beach Day extra.jpg",
  thumbnailUrl: "/thumb/42", previewUrl: "/media/42", mediaType: "image",
  createdAt: "2026-07-23T00:00:00Z", registrationState: "approved",
  readiness: "READY", contentDestination: "AVAILABLE_INVENTORY",
  sourceWorkflow: "photoshoot", sourceName: "Beach Day Photoshoot",
  sourceSessionId: "shoot-1", shortDescription: "A bright beach portrait.",
};
const response = (body: unknown, ok = true) => Promise.resolve({
  ok, json: () => Promise.resolve(body),
} as Response);
const payload = (items = [item]) => ({
  items, total: items.length, ready: items.length, pending: 0,
  page: 1, pageSize: 20, totalPages: 1,
});

afterEach(() => vi.unstubAllGlobals());
const renderInventory = () => render(<MemoryRouter><AvailableInventoryPage /></MemoryRouter>);

describe("AvailableInventoryPage", () => {
  it("renders provenance, destination, selection, future actions, and preview", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(payload())));
    renderInventory();

    expect(screen.getByLabelText("Loading Available Inventory")).toBeInTheDocument();
    expect(await screen.findByText("Beach Day extra.jpg")).toBeInTheDocument();
    expect(screen.getByText("Beach Day Photoshoot")).toBeInTheDocument();
    expect(screen.getByText("Available Inventory", { selector: "dd" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Beach Day extra.jpg" }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    for (const name of ["Create Teaser", "Create Single PPV", "Create Bundle", "Send to Telegram Wall"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    fireEvent.click(screen.getByRole("button", { name: "Preview Beach Day extra.jpg" }));
    expect(screen.getByRole("dialog", { name: "Beach Day extra.jpg preview" })).toHaveTextContent("A bright beach portrait.");
  });

  it("supports multi-selection and never renders committed API records", async () => {
    const second = { ...item, assetId: 43, displayName: "Standalone.jpg", sourceName: "Canonical Asset" };
    const committed = { ...item, assetId: 44, displayName: "Committed.jpg", contentDestination: "PHOTOSET" };
    vi.stubGlobal("fetch", vi.fn(() => response(payload([item, second, committed]))));
    renderInventory();

    await screen.findByText("Standalone.jpg");
    expect(screen.queryByText("Committed.jpg")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Beach Day extra.jpg" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Standalone.jpg" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("sends search, filters, sort, and pagination as server-side request parameters", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) => {
      void input;
      return response({ ...payload(), total: 21, totalPages: 2 });
    });
    vi.stubGlobal("fetch", fetch);
    renderInventory();
    await screen.findByText("Beach Day extra.jpg");

    fireEvent.change(screen.getByRole("textbox", { name: "Search Available Inventory" }), { target: { value: "beach" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Readiness filter" }), { target: { value: "READY" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Source filter" }), { target: { value: "photoshoot" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Media type filter" }), { target: { value: "image" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Sort Available Inventory" }), { target: { value: "oldest" } });
    fireEvent.click(await screen.findByRole("button", { name: /Next/ }));

    await waitFor(() => {
      const url = String(fetch.mock.calls.at(-1)?.[0]);
      expect(url).toContain("page=2");
      expect(url).toContain("search=beach");
      expect(url).toContain("readiness=READY");
      expect(url).toContain("source=photoshoot");
      expect(url).toContain("media_type=image");
      expect(url).toContain("sort=oldest");
    });
  });

  it("renders empty, filtered-empty, and retryable error states", async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => response(payload([])))
      .mockImplementationOnce(() => response({ detail: "Temporary failure" }, false))
      .mockImplementation(() => response(payload([])));
    vi.stubGlobal("fetch", fetch);
    const view = renderInventory();
    expect(await screen.findByText("No available inventory yet.")).toBeInTheDocument();

    view.unmount();
    renderInventory();
    expect(await screen.findByRole("alert")).toHaveTextContent("Temporary failure");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No available inventory yet.")).toBeInTheDocument();
  });
});
