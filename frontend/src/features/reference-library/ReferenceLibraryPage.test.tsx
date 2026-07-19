import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ReferenceLibraryPage } from "./ReferenceLibraryPage";

describe("ReferenceLibraryPage", () => {
  it("loads and displays the active canonical creator reference without a placeholder", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ creator: { id: 2, name: "Ava" }, active_reference: { asset_id: 84, file_name: "ava-reference.png", media_type: "image", classification: "REFERENCE", status: "approved", is_active: true, is_favorite: true, is_canonical: true, is_protected: true, added_at: "2026-01-01T00:00:00Z", last_used_at: "2026-07-18T00:00:00Z", creator_profile_id: 2, image_url: "/api/v1/reference-library/active/image" } }), { status: 200, headers: { "content-type": "application/json" } }))));
    render(<MemoryRouter><ReferenceLibraryPage /></MemoryRouter>);

    expect(await screen.findByRole("img", { name: "Ava active canonical reference" })).toHaveAttribute("src", "/api/v1/reference-library/active/image");
    expect(screen.getByText("Ava · Profile #2")).toBeInTheDocument();
    expect(screen.getByText("ava-reference.png")).toBeInTheDocument();
    expect(screen.getByText("Canonical")).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });
});
