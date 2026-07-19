import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import { PostedContentPage } from "./PostedContentPage";

const jsonResponse = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response);

const items = [
  { content_id: "posted-x", platform: "X", posted_at: "2026-07-03T00:00:00Z", caption: "X launch caption", creator: "Ava", creator_profile_id: 7, generation_library_id: "image-x", provider: "seedream_5_0_pro", prompt: "Gold portrait", file_location: "D:/Posted/X/image-x.png", media_url: "/x.png" },
  { content_id: "posted-telegram", platform: "Telegram", posted_at: "2026-07-02T00:00:00Z", caption: "Telegram update", creator: "Ava", creator_profile_id: 7, generation_library_id: "image-t", provider: "wan_2_7", prompt: "Studio portrait", file_location: "D:/Posted/Telegram/image-t.png", media_url: "/telegram.png" },
];

afterEach(() => vi.restoreAllMocks());

describe("PostedContentPage", () => {
  it("is removed from Publishing navigation", () => {
    const publishing = navigationGroups.find((group) => group.label === "Publishing");
    expect(publishing?.items.map((item) => item.label)).toEqual(["Publishing"]);
  });

  it("renders existing images and opens the metadata preview", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(jsonResponse({ items, total: 2 }));
    render(<PostedContentPage />);
    expect(await screen.findByRole("img", { name: "X posted content" })).toHaveAttribute("src", "/x.png");
    fireEvent.click(screen.getByRole("button", { name: "Preview X post" }));
    expect(screen.getByRole("dialog", { name: "Posted content preview" })).toBeInTheDocument();
    expect(screen.getByText("Gold portrait")).toBeInTheDocument();
    expect(screen.getByText("D:/Posted/X/image-x.png")).toBeInTheDocument();
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
});
