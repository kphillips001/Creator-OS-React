import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreatorLifestylePage } from "./CreatorLifestylePage";
import type { CreatorLifestyleDocument } from "./types";

const document: CreatorLifestyleDocument = {
  id: 1,
  creator_profile_id: 2,
  fanvue_account_id: "2",
  career: "Ava works in marketing and events.",
  lifestyle_overview: "Ava loves the coast and mountains.",
  favorite_activities: "Ava enjoys:\n\n- hiking\n- lakes\n- coffee shops",
  weekend_escapes: "Cabins, camping, beaches, and road trips.",
  small_town_roots: "Ava values community and a slower pace.",
  outdoor_lifestyle: "Outdoor life is a natural part of Ava's routine.",
  personal_style: "Feminine, fitted, flattering, stylish, and confident.",
  created_at: "2026-07-27T14:00:00",
  updated_at: "2026-07-27T14:00:00",
};

const response = (body: unknown, ok = true) => Promise.resolve({
  ok,
  json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.unstubAllGlobals());

describe("CreatorLifestylePage", () => {
  it("loads seven large editable lifestyle sections", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(document)));
    render(<CreatorLifestylePage />);

    expect(await screen.findByLabelText(/Career/)).toHaveValue(document.career);
    expect(screen.getByLabelText(/Lifestyle Overview/)).toHaveValue(document.lifestyle_overview);
    expect(screen.getByLabelText(/Favorite Activities/)).toHaveValue(document.favorite_activities);
    expect(screen.getByLabelText(/Weekend Escapes/)).toHaveValue(document.weekend_escapes);
    expect(screen.getByLabelText(/Small-Town Roots/)).toHaveValue(document.small_town_roots);
    expect(screen.getByLabelText(/Outdoor Lifestyle/)).toHaveValue(document.outdoor_lifestyle);
    expect(screen.getByLabelText(/Personal Style/)).toHaveValue(document.personal_style);
    expect(screen.getAllByRole("textbox")).toHaveLength(7);
    expect(screen.getByText(/It is separate from Personality, Social Creative Direction, World knowledge, and Prompt Generation/)).toBeInTheDocument();
  });

  it("saves only lifestyle document fields and renders persisted edits", async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => response(document))
      .mockImplementationOnce((_url: string, options: RequestInit) => {
        const body = JSON.parse(String(options.body));
        return response({ ...document, ...body, updated_at: "2026-07-27T15:00:00" });
      });
    vi.stubGlobal("fetch", fetch);
    render(<CreatorLifestylePage />);

    const career = await screen.findByLabelText(/Career/);
    fireEvent.change(career, { target: { value: "Updated career" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Document" }));

    expect(await screen.findByText("Lifestyle saved.")).toBeInTheDocument();
    const request = fetch.mock.calls[1]?.[1];
    expect(request).toMatchObject({ method: "PUT" });
    const payload = JSON.parse(String(request?.body));
    expect(Object.keys(payload).sort()).toEqual([
      "career", "favorite_activities", "lifestyle_overview",
      "outdoor_lifestyle", "personal_style", "small_town_roots",
      "weekend_escapes",
    ]);
    expect(payload.career).toBe("Updated career");
    expect(screen.getByLabelText(/Career/)).toHaveValue("Updated career");
  });
});
