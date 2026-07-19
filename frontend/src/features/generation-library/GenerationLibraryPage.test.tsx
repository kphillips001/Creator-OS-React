import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { EditStudioPage } from "../edit-studio/EditStudioPage";
import { PhotoshootPage } from "../photoshoot/PhotoshootPage";
import { GenerationLibraryPage } from "./GenerationLibraryPage";
import type { GenerationRecord } from "./types";

const selected: GenerationRecord = {
  image_id: "selected-image", image_url: "/selected.png", provider_id: "seedream_5_0_pro",
  prompt_text: "Selected portrait", creative_mode: "premium_teaser", generation_date: "2026-01-01T00:00:00Z",
  status: "active", generation_job_id: "job-1", generation_request_id: "request-1",
  generation_result_id: "result-1", prompt_plan_id: "plan-1", reference_asset_id: null,
  imported_asset_id: null, provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
};

const jsonResponse = (body: unknown, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  json: () => Promise.resolve(body),
  text: () => Promise.resolve(JSON.stringify(body)),
} as Response);

afterEach(() => vi.restoreAllMocks());

describe("Generation Library Edit Studio handoff", () => {
  it("awaits the Photoshoot handoff and navigates with the selected seed", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [] });
      if (url.endsWith("/selected-image/photoshoot")) return jsonResponse({ success: true, image_id: "selected-image", session_id: "session-1", status: "pending_photoshoot", redirect: "/content/photoshoot" });
      if (url.endsWith("/api/v1/photoshoot/context")) return jsonResponse({ creator_profile_exists: true, pending_photoshoot: { ...selected, status: "pending_photoshoot" }, active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: selected.provider_id }, provider_list: [], creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "seed-request", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: { ...selected, status: "pending_photoshoot" } }] });
      return jsonResponse({ error: "Unexpected request" }, 500);
    });
    render(<MemoryRouter initialEntries={["/library/generations"]}><Routes><Route path="/library/generations" element={<GenerationLibraryPage />} /><Route path="/content/photoshoot" element={<PhotoshootPage />} /></Routes></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Create Photoshoot/ }));
    expect(await screen.findByText("Shot 1 (Seed)")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Selected portrait" })[0]).toHaveAttribute("src", "/selected.png");
    expect(fetch).toHaveBeenCalledWith("/api/v1/generation-library/selected-image/photoshoot", { method: "POST" });
  });

  it("blocks duplicate Photoshoot clicks while the backend handoff is pending", async () => {
    let resolveHandoff!: (value: Response) => void;
    const handoff = new Promise<Response>((resolve) => { resolveHandoff = resolve; });
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [] });
      if (url.endsWith("/selected-image/photoshoot")) return handoff;
      return jsonResponse({ error: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    const button = await screen.findByRole("button", { name: /Create Photoshoot/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetch.mock.calls.filter(([input]) => String(input).endsWith("/selected-image/photoshoot"))).toHaveLength(1);
    resolveHandoff(await jsonResponse({ success: true, image_id: "selected-image", session_id: "session-1", status: "pending_photoshoot", redirect: "/content/photoshoot" }));
  });
  it("creates backend pending state, navigates, and renders the selected pending image", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1,
        providers: ["seedream_5_0_pro"], modes: ["premium_teaser"],
      });
      if (url.endsWith("/api/v1/generation-library/selected-image/edit")) return jsonResponse({
        success: true, message: "Image opened in Edit Studio.", image_id: "selected-image",
        status: "pending_edit", review_state: "pending_edit", context_refresh: true,
        source_image_url: "/api/v1/edit-studio/pending-source/image?image_id=selected-image&v=1",
        redirect: "/content/edit",
      });
      if (url.endsWith("/api/v1/edit-studio/context")) return jsonResponse({
        creator_profile_exists: true,
        pending_source: { ...selected, status: "pending_edit" },
        candidate: null,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
      if (url.endsWith("/api/v1/edit-studio/references")) return jsonResponse([]);
      return jsonResponse({ error: "Unexpected request" }, 500);
    });

    render(
      <MemoryRouter initialEntries={["/library/generations"]}>
        <Routes>
          <Route path="/library/generations" element={<GenerationLibraryPage />} />
          <Route path="/content/edit" element={<EditStudioPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Edit Image/ }));

    expect(await screen.findByRole("heading", { name: "Selected Source Image" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Selected portrait" })).toHaveAttribute("src", "/selected.png");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/selected-image/edit",
      { method: "POST" },
    );
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/edit-studio/context"),
      expect.any(Object),
    );
  });

  it("blocks duplicate handoffs and navigates only after a matching successful response", async () => {
    let resolveHandoff!: (value: Response) => void;
    const handoff = new Promise<Response>((resolve) => { resolveHandoff = resolve; });
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/api/v1/generation-library/selected-image/edit")) return handoff;
      return jsonResponse({ error: "Unexpected request" }, 500);
    });
    render(
      <MemoryRouter initialEntries={["/library/generations"]}>
        <Routes>
          <Route path="/library/generations" element={<GenerationLibraryPage />} />
          <Route path="/content/edit" element={<div>Edit destination</div>} />
        </Routes>
      </MemoryRouter>,
    );
    const button = await screen.findByRole("button", { name: /Edit Image/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetch.mock.calls.filter(([input]) => String(input).endsWith("/selected-image/edit"))).toHaveLength(1);
    expect(screen.queryByText("Edit destination")).not.toBeInTheDocument();
    resolveHandoff(await jsonResponse({
      success: true, image_id: "selected-image", status: "pending_edit", review_state: "pending_edit",
      redirect: "/content/edit",
    }));
    expect(await screen.findByText("Edit destination")).toBeInTheDocument();
  });
});

describe("Generation Library Asset registration", () => {
  it("registers an Asset and refreshes the card into its registered state", async () => {
    let registered = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: [{ ...selected, imported_asset_id: registered ? 42 : null }], total: 1,
        page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/selected-image/register")) {
        registered = true;
        return jsonResponse({ success: true, asset_id: 42, generation_id: "selected-image", already_registered: false, status: "registered", message: "Asset registered." });
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /Register Asset/ }));
    expect(await screen.findByText("Asset registered.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Already Registered/ })).toBeDisabled();
    expect(fetch).toHaveBeenCalledWith("/api/v1/generation-library/selected-image/register", { method: "POST" });
  });

  it("shows an existing registration without offering another registration", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [{ ...selected, imported_asset_id: 42 }], total: 1,
      page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: /Already Registered/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Register Asset/ })).not.toBeInTheDocument();
  });

  it("surfaces registration failures and keeps the action available", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("generation-library?")
      ? jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [] })
      : jsonResponse({ detail: "Generated image file is missing." }, 409));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Register Asset/ }));
    expect(await screen.findByText("Generated image file is missing.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Register Asset/ })).toBeEnabled();
  });

  it("keeps Create Video disabled and does not call a video endpoint", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [selected], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    const button = await screen.findByRole("button", { name: /Create Video/ });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(fetch.mock.calls.some(([input]) => String(input).includes("/video"))).toBe(false);
  });
});
