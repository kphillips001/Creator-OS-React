import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { EditStudioPage } from "../edit-studio/EditStudioPage";
import { PhotoshootPage } from "../photoshoot/PhotoshootPage";
import { BackgroundOperationsProvider } from "../background-operations/BackgroundOperationsContext";
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

function AssetHandoffProbe() {
  const location = useLocation();
  return <div>Asset destination {location.pathname}{location.search}</div>;
}

afterEach(() => { vi.restoreAllMocks(); window.sessionStorage.clear(); });

describe("Generation Library media projection", () => {
  it("selects and bulk classifies all 24 records on a full Unclassified page", async () => {
    const records = Array.from({ length: 24 }, (_, index) => ({
      ...selected, image_id: `image-${index + 1}`, media_url: `/image-${index + 1}.png`,
      content_classification: null,
    }));
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/content-classification/bulk") && init?.method === "PATCH") {
        return jsonResponse({ image_ids: records.map(record => record.image_id), classified_count: 24,
          content_classification: "NSFW", classification_source: "MANUAL" });
      }
      return jsonResponse({ records, total: 49, page: 1, pageSize: 24, totalPages: 3, providers: [], modes: [] });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.change(await screen.findByRole("combobox", { name: "Content origin" }), { target: { value: "UNCLASSIFIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: "Select All on Page" }));
    expect(screen.getByText("24 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Classify NSFW" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/content-classification/bulk",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({
        image_ids: records.map(record => record.image_id), classification: "NSFW",
      }) }),
    ));
  });

  it("requests adjacent pages and renders a 24 plus 1 boundary without skips", async () => {
    const records = Array.from({ length: 25 }, (_, index) => ({
      ...selected, image_id: `page-image-${index + 1}`, image_url: `/page-image-${index + 1}.png`,
      media_url: `/page-image-${index + 1}.png`, prompt_text: `Page image ${index + 1}`,
    }));
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true, value: vi.fn(),
    });
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      requests.push(url);
      const secondPage = url.includes("page=2");
      return jsonResponse({
        records: secondPage ? records.slice(24) : records.slice(0, 24),
        total: 25, page: secondPage ? 2 : 1, pageSize: 24, totalPages: 2,
        providers: [], modes: [],
      });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    expect(await screen.findAllByRole("button", { name: /Open generation/ })).toHaveLength(24);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(requests.some(url => url.includes("page=2"))).toBe(true));
    expect(await screen.findAllByRole("button", { name: /Open generation/ })).toHaveLength(1);
    expect(screen.getByRole("img", { name: "Page image 25" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(requests.filter(url => url.includes("page=1")).length).toBeGreaterThan(1));
    expect(await screen.findAllByRole("button", { name: /Open generation/ })).toHaveLength(24);
  });

  it("bulk classifies selected Unclassified images and refreshes canonical results", async () => {
    const second = { ...selected, image_id: "second-image", content_classification: null, classification_source: null };
    const unclassified = { ...selected, content_classification: null, classification_source: null };
    let classified = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?") && !init?.method) return jsonResponse({
        records: classified ? [] : [{ ...unclassified, media_url: "/selected.png" }, { ...second, media_url: "/second.png" }],
        total: classified ? 0 : 2, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/content-classification/bulk") && init?.method === "PATCH") {
        classified = true;
        return jsonResponse({ image_ids: ["selected-image", "second-image"], classified_count: 2, content_classification: "SFW", classification_source: "MANUAL" });
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    fireEvent.change(await screen.findByRole("combobox", { name: "Content origin" }), { target: { value: "UNCLASSIFIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: "Select All on Page" }));
    fireEvent.click(screen.getByRole("button", { name: "Classify SFW" }));

    await waitFor(() => expect(screen.getByText("2 images classified as SFW.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/content-classification/bulk",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ image_ids: ["selected-image", "second-image"], classification: "SFW" }) }),
    );
    await waitFor(() => expect(screen.getByText("No generated images match these filters.")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
  });

  it("shows bulk classification only in Unclassified and removes inspector controls", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("?")
      ? jsonResponse({ records: [{ ...selected, content_classification: null, media_url: "/selected.png" }], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] })
      : jsonResponse({ ...selected, content_classification: null }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    const filter = await screen.findByRole("combobox", { name: "Content origin" });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: /Select generation/ }));
    expect(screen.queryByRole("button", { name: "Classify SFW" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
    fireEvent.change(filter, { target: { value: "UNCLASSIFIED" } });
    expect(await screen.findByRole("button", { name: "Classify SFW" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Exit Select" }));
    fireEvent.click(await screen.findByRole("button", { name: /Open generation/ }));
    await screen.findByText("Selected portrait");
    expect(screen.queryByLabelText("Classify content")).not.toBeInTheDocument();
  });

  it("confirms and archives the current Unclassified selection in one request", async () => {
    const records = [selected, { ...selected, image_id: "second-image" }].map(record => ({
      ...record, content_classification: null, media_url: `/${record.image_id}.png`,
    }));
    let archived = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/archive/bulk") && init?.method === "POST") {
        archived = true;
        return jsonResponse({ image_ids: records.map(record => record.image_id), archived_count: 2 });
      }
      return jsonResponse({ records: archived ? [] : records, total: archived ? 0 : 2,
        page: 1, pageSize: 24, totalPages: 1, providers: [], modes: [] });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.change(await screen.findByRole("combobox", { name: "Content origin" }), { target: { value: "UNCLASSIFIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: "Select All on Page" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    const dialog = screen.getByRole("dialog", { name: "Archive 2 selected images?" });
    expect(within(dialog).getByText(/restored later/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(screen.getByText("2 images archived.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/archive/bulk",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ image_ids: ["selected-image", "second-image"] }) }),
    );
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
  });

  it("keeps bulk Archive selection and confirmation available after failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/archive/bulk") && init?.method === "POST") {
        return jsonResponse({ detail: "Archive selection is stale." }, 409);
      }
      return jsonResponse({ records: [{ ...selected, content_classification: null, media_url: "/selected.png" }],
        total: 1, page: 1, pageSize: 24, totalPages: 1, providers: [], modes: [] });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.change(await screen.findByRole("combobox", { name: "Content origin" }), { target: { value: "UNCLASSIFIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: /Select generation/ }));
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    expect(await screen.findByText("Archive selection is stale.")).toBeInTheDocument();
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Archive 1 selected image?" })).toBeInTheDocument();
  });

  it("retains the selected images when bulk classification fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/content-classification/bulk") && init?.method === "PATCH") {
        return jsonResponse({ detail: "Selection is stale." }, 409);
      }
      return jsonResponse({ records: [{ ...selected, content_classification: null, media_url: "/selected.png" }], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.change(await screen.findByRole("combobox", { name: "Content origin" }), { target: { value: "UNCLASSIFIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(await screen.findByRole("button", { name: /Select generation/ }));
    fireEvent.click(screen.getByRole("button", { name: "Classify NSFW" }));
    expect(await screen.findByText("Selection is stale.")).toBeInTheDocument();
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exit Select" })).toBeInTheDocument();
  });

  it("defaults to All Content and replaces provider, mode, and sort controls with origin filtering", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      requests.push(String(input));
      return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] });
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    const origin = await screen.findByRole("combobox", { name: "Content origin" });
    expect(origin).toHaveValue("");
    expect(screen.getByRole("option", { name: "All Content" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Unclassified" })).toHaveValue("UNCLASSIFIED");
    expect(screen.queryByRole("combobox", { name: "Provider" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Creative mode" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Sort generations" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
    expect(requests[0]).toContain("sort=newest");
    expect(requests[0]).not.toContain("contentOrigin=");

    fireEvent.change(origin, { target: { value: "NSFW" } });
    await waitFor(() => expect(requests.some((url) => url.includes("contentOrigin=NSFW"))).toBe(true));
    expect(requests.at(-1)).toContain("page=1");
    expect(requests.at(-1)).toContain("sort=newest");

    fireEvent.change(origin, { target: { value: "UNCLASSIFIED" } });
    await waitFor(() => expect(requests.some((url) => url.includes("contentOrigin=UNCLASSIFIED"))).toBe(true));
  });

  it("uses thumbnails for cards and loads canonical media details for full viewing", async () => {
    const card = {
      image_id: selected.image_id,
      image_url: "/api/v1/generation-library/selected-image/thumbnail?v=1",
      media_url: "/api/v1/generation-library/selected-image/media?v=1",
      provider_id: selected.provider_id,
      creative_mode: selected.creative_mode,
      generation_date: selected.generation_date,
      status: selected.status,
      canRegenerate: false,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: [card], total: 1, page: 1, pageSize: 20, totalPages: 1,
        providers: [selected.provider_id], modes: [selected.creative_mode],
      });
      if (url.endsWith("/api/v1/generation-library/selected-image")) return jsonResponse({
        ...selected, image_url: "/api/v1/generation-library/selected-image/media?v=1",
      });
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    const cardImage = await screen.findByRole("img", { name: "Generated image selected-image" });
    expect(cardImage).toHaveAttribute("src", card.image_url);
    fireEvent.click(screen.getByRole("button", { name: /Open generation/ }));
    expect(await screen.findByRole("img", { name: selected.prompt_text })).toHaveAttribute(
      "src", "/api/v1/generation-library/selected-image/media?v=1",
    );
  });

  it("stages from the viewer and refreshes the canonical staged card onto page one", async () => {
    const card = { ...selected, media_url: "/selected.png", is_staged: false };
    let staged = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?") && !init?.method) return jsonResponse({
        records: [{ ...card, is_staged: staged, staged_at: staged ? "2026-08-15T10:00:00Z" : null }],
        total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/selected-image/posting-stage") && init?.method === "PUT") {
        staged = true;
        return jsonResponse({ ...selected, is_staged: true, staged_at: "2026-08-15T10:00:00Z" });
      }
      if (url.endsWith("/selected-image")) return jsonResponse({ ...selected, is_staged: staged });
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: /Open generation/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Stage for Posting" }));

    await waitFor(() => expect(screen.getByText("STAGED")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/selected-image/posting-stage",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ is_staged: true }) }),
    );
  });
});

describe("Generation Library Edit Studio handoff", () => {
  it("awaits the Photoshoot handoff and navigates with the selected seed", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] });
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
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] });
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
        records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1,
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
        records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
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

describe("Generation Library Asset Library move", () => {
  it("keeps active assembled Photoshoot progress in the sticky workspace", async () => {
    const operation = {
      operationId: "operation-1", operationType: "assembled_photoshoot_intake",
      originatingWorkspace: "generation_library", subjectType: "assembled_photoshoot_intake",
      subjectId: "intake-1", status: "WAITING_EXTERNAL", progressCurrent: 6, progressTotal: 8,
      progressPercent: 75, currentStage: "WAITING_INTELLIGENCE",
      stageMessage: "Waiting for canonical Content Intelligence", createdAt: "2026-08-12T12:00:00Z",
      startedAt: "2026-08-12T12:00:01Z", completedAt: null, resultLocation: null,
      resultReference: null, errorCode: null, errorMessage: null, cancellationSupported: false,
      metadata: { intake_id: "intake-1", image_count: 6 },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/background-operations?status=active")) {
        return jsonResponse({ success: true, operations: [operation] });
      }
      if (url.includes("/background-operations?status=recent")) {
        return jsonResponse({ success: true, operations: [] });
      }
      if (url.endsWith("/background-operations/operation-1")) {
        return jsonResponse({ success: true, operation });
      }
      if (url.includes("/api/v1/generation-library?")) {
        return jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20,
          totalPages: 1, providers: [], modes: [] });
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });

    render(<MemoryRouter><BackgroundOperationsProvider pollMilliseconds={60_000}>
      <GenerationLibraryPage />
    </BackgroundOperationsProvider></MemoryRouter>);

    const progress = (await screen.findByText("Creating Photoshoot…")).closest<HTMLElement>("[role='status']")!;
    expect(within(progress).getByText("Creating Photoshoot…")).toBeInTheDocument();
    expect(within(progress).getByText("Waiting for canonical Content Intelligence")).toBeInTheDocument();
    expect(progress.closest(".generation-library__sticky-workspace")).not.toBeNull();
  });

  it("shows selection controls, supports multiple selection, and clears safely", async () => {
    const second = { ...selected, image_id: "second-image" };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [selected, second], total: 2, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Select" }));
    const move = screen.getByRole("button", { name: "Create Photoshoot" });
    expect(move).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Select generation selected-image" }));
    fireEvent.click(screen.getByRole("button", { name: "Select generation second-image" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(move).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(move).toBeDisabled();
  });

  it("collects cover and submits deterministic order without a manual name", async () => {
    const second = { ...selected, image_id: "second-image" };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("generation-library?")) return jsonResponse({ records: [selected, second], total: 2, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] });
      if (url.endsWith("/generation-library/photoshoots/import")) return jsonResponse({ intakeId: "intake-1", operationId: "operation-1", operationStatus: "QUEUED", created: true, deliverableId: null, sourceKind: "GENERATION_LIBRARY_IMPORT" });
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select All on Page" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create Photoshoot" }));
    const dialog = screen.getByRole("dialog", { name: "Create Photoshoot" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("2 images selected")).toBeInTheDocument();
    expect(within(dialog).queryByText(/price/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/Chat|Content Wall|Fanvue/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Move shot/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Photoshoot name")).not.toBeInTheDocument();
    expect(within(dialog).queryByDisplayValue("New Photoshoot")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use as Cover" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Create Photoshoot" })).getByRole("button", { name: "Create Photoshoot" }));
    expect(await screen.findByText("Creating Photoshoot…")).toBeInTheDocument();
    const calls = fetch.mock.calls.filter(([input]) => String(input).endsWith("/generation-library/photoshoots/import"));
    expect(calls).toHaveLength(1);
    const request = JSON.parse(String(calls[0]?.[1]?.body));
    expect(request).toMatchObject({ imageIds: ["selected-image", "second-image"], heroImageId: "second-image" });
    expect(request).not.toHaveProperty("displayName");
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("retains bulk selection when the atomic move fails", async () => {
    const second = { ...selected, image_id: "second-image" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("generation-library?")
      ? jsonResponse({ records: [selected, second], total: 2, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] })
      : jsonResponse({ detail: "Ownership conflict" }, 409));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select All on Page" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Photoshoot" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Create Photoshoot" })).getByRole("button", { name: "Create Photoshoot" }));
    expect(await screen.findByText("Ownership conflict")).toBeInTheDocument();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Deselect generation selected-image/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Open generation/ })).toHaveLength(2);
  });

  it("ignores the retired Bundle Studio selection query", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] }));
    render(<MemoryRouter initialEntries={["/library/generations?bundleSelect=1"]}><GenerationLibraryPage /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "Select" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Exit Select" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
  });

  it("removes the per-card Bundle action while preserving unrelated actions", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Asset Library" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move to Bundle Studio" })).not.toBeInTheDocument();
  });

  it("uses a directional icon and reserves the star for future registration", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);

    const button = await screen.findByRole("button", { name: "Move to Asset Library" });
    expect(button).toHaveAttribute("title", "Move to Asset Library");
    expect(button).not.toHaveTextContent("⭐");
    expect(button.querySelector(".lucide-move-right")).toBeInTheDocument();
  });

  it("navigates a successfully moved generation to its exact canonical Asset", async () => {
    let moved = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: moved ? [] : [selected], total: moved ? 0 : 1,
        page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/selected-image/move-to-asset-library")) {
        moved = true;
        return jsonResponse({ success: true, generation_id: "selected-image", asset_id: 51, already_moved: false, status: "analyzing", analysis_status: "NUDENET_PENDING", message: "Asset is registered. Intelligence analysis is in progress." });
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter initialEntries={["/library/generations"]}><Routes><Route path="/library/generations" element={<GenerationLibraryPage />} /><Route path="/library/assets" element={<AssetHandoffProbe />} /></Routes></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: "Move to Asset Library" }));
    expect(await screen.findByText("Asset destination /library/assets?assetType=images")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("creator-os.asset-library.moved-asset-id")).toBe("51");
    expect(fetch).toHaveBeenCalledWith("/api/v1/generation-library/selected-image/move-to-asset-library", { method: "POST" });
  });

  it("adds a generation to Teasers and opens its canonical Teaser Asset", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/generation-library?")) return jsonResponse({
        records: [selected], total: 1, page: 1, pageSize: 24, totalPages: 1, providers: [], modes: [],
      });
      if (url.endsWith("/selected-image/add-to-teasers")) return jsonResponse({
        success: true, generation_id: "selected-image", asset_id: 73,
        already_moved: false, status: "analyzing", analysis_status: "NUDENET_PENDING",
        message: "Added to Teasers. Asset Intelligence is analyzing.",
      });
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });
    render(<MemoryRouter initialEntries={["/library/generations"]}><Routes><Route path="/library/generations" element={<GenerationLibraryPage />} /><Route path="/library/assets" element={<AssetHandoffProbe />} /></Routes></MemoryRouter>);
    const teaserButton = await screen.findByRole("button", { name: "Add to Teasers" });
    expect(teaserButton).toHaveClass("library-action-button");
    expect(teaserButton).not.toHaveClass("library-action-button--accent");
    fireEvent.click(teaserButton);
    expect(await screen.findByText("Asset destination /library/assets?assetType=teasers")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("creator-os.asset-library.moved-asset-id")).toBe("73");
    expect(fetch).toHaveBeenCalledWith("/api/v1/generation-library/selected-image/add-to-teasers", { method: "POST" });
  });

  it("surfaces move failures and keeps the action available", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("generation-library?")
      ? jsonResponse({ records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] })
      : jsonResponse({ detail: "Generated image file is missing." }, 409));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Move to Asset Library" }));
    expect(await screen.findByText("Generated image file is missing.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Asset Library" })).toBeEnabled();
    expect(window.sessionStorage.getItem("creator-os.asset-library.moved-asset-id")).toBeNull();
  });

  it("opens the shared Video Studio without calling a duplicate video endpoint", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      records: [selected], total: 1, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [],
    }));
    render(<MemoryRouter><GenerationLibraryPage /></MemoryRouter>);
    const button = await screen.findByRole("button", { name: /Create Video/ });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(fetch.mock.calls.some(([input]) => String(input).includes("/video"))).toBe(false);
  });
});

describe("Generation Library regeneration eligibility", () => {
  it("shows the canonical action only for eligible records and hands off only the source ID", async () => {
    const eligible = { ...selected, canRegenerate: true };
    const legacy = { ...selected, image_id: "legacy-image", canRegenerate: false };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({ records: [eligible, legacy], total: 2, page: 1, pageSize: 20, totalPages: 1, providers: [], modes: [] }));
    render(<MemoryRouter initialEntries={["/library/generations"]}><Routes><Route path="/library/generations" element={<GenerationLibraryPage />} /><Route path="/studio/regeneration" element={<div>Regeneration destination</div>} /></Routes></MemoryRouter>);
    const actions = await screen.findAllByRole("button", { name: "Regenerate from same recipe" });
    expect(actions).toHaveLength(1);
    expect(actions[0]!).toHaveAttribute("title", "Regenerate from same recipe");
    fireEvent.click(actions[0]!);
    expect(await screen.findByText("Regeneration destination")).toBeInTheDocument();
  });
});
