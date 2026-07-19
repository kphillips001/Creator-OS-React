import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetLibraryPage } from "./AssetLibraryPage";

const asset = {
  assetId: 42,
  fileName: "portrait.png",
  mediaType: "image",
  classification: "premium",
  status: "approved",
  createdAt: "2026-01-02T00:00:00Z",
  tags: ["portrait"],
  themes: ["studio"],
  isReference: false,
  isCanonicalReference: false,
  mediaAvailable: true,
  imageUrl: "/api/v1/assets/42/media",
};

const response = (body: unknown, ok = true) => Promise.resolve({
  ok,
  json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.restoreAllMocks());

describe("AssetLibraryPage", () => {
  it("renders assets, loads details, and opens the media preview", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/42") return response({ ...asset, registrationSource: "generation_library" });
      return response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["premium"] });
    });
    render(<AssetLibraryPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview Asset 42" }));
    expect(screen.getByRole("dialog", { name: "Asset 42 preview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    fireEvent.click(screen.getByRole("button", { name: /Asset #42/ }));

    expect(await screen.findByText("generation_library")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42", { cache: "no-store" });
  });

  it("sends search and filter values and paginates", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => response({
      assets: [asset], total: 36, page: String(input).includes("page=2") ? 2 : 1,
      pageSize: 18, totalPages: 2, classifications: ["premium"],
    }));
    render(<AssetLibraryPage />);
    await screen.findByText("Page 1 of 2");
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "portrait" } });
    fireEvent.change(screen.getByLabelText("Media type"), { target: { value: "image" } });
    fireEvent.change(screen.getByLabelText("Classification"), { target: { value: "premium" } });
    fireEvent.click(await screen.findByRole("button", { name: /Next/ }));

    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input);
      return url.includes("page=2") && url.includes("search=portrait") && url.includes("media_type=image") && url.includes("classification=premium");
    })).toBe(true));
  });

  it("shows empty and error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(await response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    const view = render(<AssetLibraryPage />);
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    view.unmount();

    fetch.mockResolvedValueOnce(await response({ detail: "Asset service unavailable." }, false));
    render(<AssetLibraryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Asset service unavailable.");
  });
});
