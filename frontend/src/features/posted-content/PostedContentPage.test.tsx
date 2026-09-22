import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import { PostedContentPage } from "./PostedContentPage";

const jsonResponse = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response);

const items = [
  { content_id: "posted-x", platform: "X", posted_at: "2026-07-03T00:00:00Z", caption: "X launch caption", creator: "Ava", creator_profile_id: 7, generation_library_id: "image-x", provider: "seedream_5_0_pro", prompt: "Gold portrait", file_location: "D:/Posted/X/image-x.png", media_url: "/x.png", media_type: "image", move_eligible: true },
  { content_id: "posted-telegram", platform: "Telegram", posted_at: "2026-07-02T00:00:00Z", caption: "Telegram update", creator: "Ava", creator_profile_id: 7, generation_library_id: "image-t", provider: "wan_2_7", prompt: "Studio portrait", file_location: "D:/Posted/Telegram/image-t.png", media_url: "/telegram.png", media_type: "image", move_eligible: false },
];

afterEach(() => vi.restoreAllMocks());

describe("PostedContentPage", () => {
  it("has no Publishing navigation group", () => {
    const publishing = navigationGroups.find((group) => group.label === "Publishing");
    expect(publishing).toBeUndefined();
  });

  it("renders existing images and opens the metadata preview", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(jsonResponse({ items, total: 2 }));
    render(<PostedContentPage />);
    expect(await screen.findByRole("img", { name: "X posted content" })).toHaveAttribute("src", "/x.png");
    fireEvent.click(screen.getByRole("button", { name: "Preview X post" }));
    expect(screen.getByRole("dialog", { name: "Posted content preview" })).toBeInTheDocument();
    expect(screen.getByText("Gold portrait")).toBeInTheDocument();
    expect(screen.getByText("D:/Posted/X/image-x.png")).toBeInTheDocument();
    expect(document.querySelector(".generation-card--staged")).toBeNull();
    expect(screen.queryByText("STAGED")).not.toBeInTheDocument();
  });

  it("supports search and platform filtering", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(jsonResponse({ items, total: 2 }));
    render(<PostedContentPage />);
    await screen.findByText("X launch caption");
    fireEvent.change(screen.getByPlaceholderText("Search posted content"), { target: { value: "Telegram update" } });
    expect(screen.queryByText("X launch caption")).not.toBeInTheDocument();
    expect(screen.getByText("Telegram update")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search posted content"), { target: { value: "" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Platform" }), { target: { value: "X" } });
    expect(screen.getByText("X launch caption")).toBeInTheDocument();
    expect(screen.queryByText("Telegram update")).not.toBeInTheDocument();
  });

  it("shows the required empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(jsonResponse({ items: [], total: 0 }));
    render(<PostedContentPage />);
    expect(await screen.findByText("No posted content yet.")).toBeInTheDocument();
    expect(screen.getByText("Images posted through Creator_OS will automatically appear here.")).toBeInTheDocument();
  });

  it("confirms, cancels, and completes an eligible per-card move", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/posted-x/move-to-generation-library") && init?.method === "POST") {
        return jsonResponse({ success: true, message: "Image moved to Generation Library. Publication history was preserved." });
      }
      return jsonResponse({ items, total: 2 });
    });
    render(<PostedContentPage />);
    await screen.findByText("X launch caption");
    expect(screen.getAllByRole("button", { name: "Move to Generation Library" })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Move to Generation Library" }));
    expect(screen.getByRole("dialog", { name: "Move back to Generation Library?" })).toHaveTextContent("publication history will remain intact");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("X launch caption")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move to Generation Library" }));
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(screen.queryByText("X launch caption")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("Publication history was preserved");
    expect(fetch).toHaveBeenCalledWith("/api/v1/posted-content/posted-x/move-to-generation-library", { method: "POST" });
    expect(screen.getByText("Telegram update")).toBeInTheDocument();
  });

  it("keeps the card visible when a move fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      if (init?.method === "POST") return Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: "Published image file is unavailable." }) } as Response);
      return jsonResponse({ items: [items[0]], total: 1 });
    });
    render(<PostedContentPage />);
    await screen.findByText("X launch caption");
    fireEvent.click(screen.getByRole("button", { name: "Move to Generation Library" }));
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Published image file is unavailable");
    expect(screen.getByText("X launch caption")).toBeInTheDocument();
  });

  it("keeps the compact action and confirmation usable at 150 percent zoom", async () => {
    document.documentElement.style.zoom = "150%";
    vi.spyOn(globalThis, "fetch").mockReturnValue(jsonResponse({ items: [items[0]], total: 1 }));
    render(<PostedContentPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Move to Generation Library" }));
    expect(screen.getByRole("dialog", { name: "Move back to Generation Library?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move" })).toBeEnabled();
    document.documentElement.style.zoom = "";
  });
});
