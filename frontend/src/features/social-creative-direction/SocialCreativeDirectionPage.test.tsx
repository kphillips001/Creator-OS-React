import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SocialCreativeDirectionPage } from "./SocialCreativeDirectionPage";
import type { SocialCreativeDirectionDocument } from "./types";

const document: SocialCreativeDirectionDocument = {
  id: 1,
  creator_profile_id: 2,
  fanvue_account_id: "2",
  purpose: "Create visually engaging public social content.",
  wardrobe: "Ava should wear believable everyday clothing.\n\n- leggings",
  visual_style: "Natural, confident, approachable, playful, and feminine.",
  seasonal_guidance: "Maintain believable seasonal consistency.",
  things_to_avoid: "Avoid:\n\n- repetitive outfits",
  created_at: "2026-07-27T12:00:00",
  updated_at: "2026-07-27T12:00:00",
};

const response = (body: unknown, ok = true) => Promise.resolve({
  ok,
  json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.unstubAllGlobals());

describe("SocialCreativeDirectionPage", () => {
  it("loads the account-scoped document as five large editable sections", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(document)));
    render(<SocialCreativeDirectionPage />);

    expect(await screen.findByLabelText(/Purpose/)).toHaveValue(document.purpose);
    expect(screen.getByLabelText(/Wardrobe/)).toHaveValue(document.wardrobe);
    expect(screen.getByLabelText(/Visual Style/)).toHaveValue(document.visual_style);
    expect(screen.getByLabelText(/Seasonal Guidance/)).toHaveValue(document.seasonal_guidance);
    expect(screen.getByLabelText(/Things To Avoid/)).toHaveValue(document.things_to_avoid);
    expect(screen.getAllByRole("textbox")).toHaveLength(5);
    expect(screen.getByText(/It is separate from Personality, Visual Identity, and Prompt Generation/)).toBeInTheDocument();
  });

  it("saves only the five document fields and shows the persisted response", async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => response(document))
      .mockImplementationOnce((_url: string, options: RequestInit) => {
        const body = JSON.parse(String(options.body));
        return response({ ...document, ...body, updated_at: "2026-07-27T13:00:00" });
      });
    vi.stubGlobal("fetch", fetch);
    render(<SocialCreativeDirectionPage />);

    const purpose = await screen.findByDisplayValue(document.purpose);
    fireEvent.change(purpose, { target: { value: "Updated direction" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Document" }));

    expect(await screen.findByText("Social Creative Direction saved.")).toBeInTheDocument();
    const request = fetch.mock.calls[1]?.[1];
    expect(request).toMatchObject({ method: "PUT" });
    const payload = JSON.parse(String(request?.body));
    expect(Object.keys(payload).sort()).toEqual([
      "purpose", "seasonal_guidance", "things_to_avoid",
      "visual_style", "wardrobe",
    ]);
    expect(payload.purpose).toBe("Updated direction");
    expect(screen.getByDisplayValue("Updated direction")).toBeInTheDocument();
  });
});
