import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VersionHistoryPage } from "./VersionHistoryPage";
import { navigationGroups } from "../../app/navigation/navigation";

const jsonResponse = (body: unknown, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  json: () => Promise.resolve(body),
} as Response);

const record = {
  image_id: "asset-1", image_url: "/current.png", provider_id: "nano_banana_pro",
  prompt_text: "Current portrait", creative_mode: "premium_teaser", generation_date: "2026-07-03T00:00:00Z",
  status: "active", generation_job_id: "job-1", generation_request_id: "request-1",
  generation_result_id: "result-1", prompt_plan_id: "plan-3", reference_asset_id: null,
  imported_asset_id: null, provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
  creator_profile_id: 7,
};

function mockHistory(archived = true, restoreStatus = 200) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/api/generation-library?")) return jsonResponse({
      records: [record], total: 1, page: 1, pageSize: 18, totalPages: 1, providers: [], modes: [],
    });
    if (url.endsWith("/api/v1/generation-library/asset-1/versions")) return jsonResponse({
      generation_library_record_id: "asset-1", current_version: 3,
      versions: [
        { generation_library_record_id: "asset-1", version_number: 3, is_current: true, approval_timestamp: "2026-07-03T00:00:00Z", provider_id: "nano_banana_pro", prompt: "Current portrait", prompt_plan_id: "plan-3", generation_metadata: {}, original_file_path: "current.png", archived_file_path: null, edit_source: "edit_studio", image_url: "/current.png" },
        ...(archived ? [
          { generation_library_record_id: "asset-1", version_number: 1, is_current: false, approval_timestamp: "2026-07-01T00:00:00Z", provider_id: "seedream_4_5", prompt: "First portrait", prompt_plan_id: "plan-1", generation_metadata: { source: "content_studio" }, original_file_path: "first.png", archived_file_path: "archive/one.png", edit_source: "edit_studio", image_url: "/one.png" },
          { generation_library_record_id: "asset-1", version_number: 2, is_current: false, approval_timestamp: "2026-07-02T00:00:00Z", provider_id: "wan_2_7", prompt: "Second portrait", prompt_plan_id: "plan-2", generation_metadata: { model: "wan" }, original_file_path: "second.png", archived_file_path: "archive/two.png", edit_source: "edit_studio", image_url: "/two.png" },
        ] : []),
      ],
    });
    if (url.endsWith("/api/v1/generation-library/asset-1/versions/1/restore") && init?.method === "POST") {
      if (restoreStatus !== 200) return jsonResponse({ detail: "Archive media missing." }, restoreStatus);
      return jsonResponse({
        success: true,
        version_history: {
          generation_library_record_id: "asset-1", current_version: 4,
          versions: [
            { generation_library_record_id: "asset-1", version_number: 4, is_current: true, approval_timestamp: "2026-07-04T00:00:00Z", provider_id: "seedream_4_5", prompt: "First portrait", prompt_plan_id: "plan-1", generation_metadata: { restored_from_version: 1 }, original_file_path: "restored.png", archived_file_path: null, edit_source: "version_restore", image_url: "/restored.png?v=4" },
            { generation_library_record_id: "asset-1", version_number: 3, is_current: false, approval_timestamp: "2026-07-03T00:00:00Z", provider_id: "nano_banana_pro", prompt: "Current portrait", prompt_plan_id: "plan-3", generation_metadata: {}, original_file_path: "current.png", archived_file_path: "archive/three.png", edit_source: "edit_studio", image_url: "/three.png" },
            { generation_library_record_id: "asset-1", version_number: 2, is_current: false, approval_timestamp: "2026-07-02T00:00:00Z", provider_id: "wan_2_7", prompt: "Second portrait", prompt_plan_id: "plan-2", generation_metadata: {}, original_file_path: "second.png", archived_file_path: "archive/two.png", edit_source: "edit_studio", image_url: "/two.png" },
            { generation_library_record_id: "asset-1", version_number: 1, is_current: false, approval_timestamp: "2026-07-01T00:00:00Z", provider_id: "seedream_4_5", prompt: "First portrait", prompt_plan_id: "plan-1", generation_metadata: {}, original_file_path: "first.png", archived_file_path: "archive/one.png", edit_source: "edit_studio", image_url: "/one.png" },
          ],
        },
      });
    }
    return jsonResponse({}, 404);
  });
}

afterEach(() => vi.restoreAllMocks());

describe("VersionHistoryPage", () => {
  it("is consolidated beneath Archive in System navigation", () => {
    const system = navigationGroups.find((group) => group.label === "System");
    expect(system?.items.map((item) => item.label)).toEqual([
      "Settings", "Diagnostics", "Archive",
    ]);
  });

  it("renders the current asset and archived timeline newest to oldest", async () => {
    mockHistory();
    render(<VersionHistoryPage />);

    expect(await screen.findByRole("heading", { name: "Current Version" })).toBeInTheDocument();
    const previous = screen.getByRole("heading", { name: "Previous Versions" }).closest("section");
    const headings = within(previous as HTMLElement).getAllByRole("heading", { level: 4 });
    expect(headings.map((heading) => heading.textContent)).toEqual(["Version 2", "Version 1"]);
    screen.getAllByRole("button", { name: "Restore" }).forEach((button) => {
      expect(button).toBeEnabled();
    });
  });

  it("confirms, restores once, and refreshes only the selected asset in place", async () => {
    const fetch = mockHistory();
    render(<VersionHistoryPage />);
    const restoreButtons = await screen.findAllByRole("button", { name: "Restore" });
    fireEvent.click(restoreButtons[1]!);
    expect(screen.getByRole("heading", { name: "Restore Version 1?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore Version" }));
    expect(await screen.findByText("Version 1 restored as Version 4.")).toBeInTheDocument();
    expect(screen.getByText("Restored from Version 1")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Version 4" })).toHaveAttribute("src", "/restored.png?v=4");
    expect(fetch.mock.calls.filter(([input, init]) => String(input).endsWith("/versions/1/restore") && init?.method === "POST")).toHaveLength(1);
    expect(fetch.mock.calls.filter(([input]) => String(input).includes("/api/generation-library?"))).toHaveLength(1);
  });

  it("cancels without submitting and preserves backend restore errors", async () => {
    const fetch = mockHistory(true, 409);
    render(<VersionHistoryPage />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Restore" }))[1]!);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Restore" })[1]!);
    fireEvent.click(screen.getByRole("button", { name: "Restore Version" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Archive media missing.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("prevents duplicate restore submissions while one request is pending", async () => {
    const fetch = mockHistory();
    const original = fetch.getMockImplementation()!;
    let resolveRestore!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveRestore = resolve; });
    fetch.mockImplementation((input, init) => String(input).endsWith("/versions/1/restore")
      ? pending
      : original(input, init));
    render(<VersionHistoryPage />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Restore" }))[1]!);
    const confirm = screen.getByRole("button", { name: "Restore Version" });
    fireEvent.click(confirm);
    const pendingConfirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Restoring…" });
    expect(pendingConfirm).toBeDisabled();
    fireEvent.click(pendingConfirm);
    expect(fetch.mock.calls.filter(([input]) => String(input).endsWith("/versions/1/restore"))).toHaveLength(1);
    resolveRestore(await jsonResponse({ detail: "Stopped for test." }, 409));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stopped for test.");
  });

  it("opens a thumbnail preview and filters histories by search", async () => {
    mockHistory();
    render(<VersionHistoryPage />);
    const thumbnail = await screen.findByRole("button", { name: "Preview Version 2" });
    fireEvent.click(thumbnail);
    expect(screen.getByRole("dialog", { name: "Version 2 preview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    fireEvent.change(screen.getByPlaceholderText("Search versions"), { target: { value: "not present" } });
    expect(screen.getByText("No version history matches these filters.")).toBeInTheDocument();
  });

  it("shows the archive empty state when current assets have no previous versions", async () => {
    mockHistory(false);
    render(<VersionHistoryPage />);
    expect(await screen.findByText("No archived versions yet.")).toBeInTheDocument();
    expect(screen.getByText("Approved edits will automatically appear here.")).toBeInTheDocument();
  });
});
