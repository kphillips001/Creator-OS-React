import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FanvueApiExplorerPage } from "./FanvueApiExplorerPage";
import { FanvueJsonViewer } from "./FanvueJsonViewer";

const responseBody = {
  endpoint: "/media-links",
  requestParams: {},
  httpStatus: 200,
  elapsedMs: 12.4,
  recordCount: 1,
  cursor: null,
  nextPage: null,
  pagination: {},
  apiVersion: "2025-06-26",
  oauthScopes: ["read:media"],
  headers: { "content-type": "application/json" },
  body: {
    items: [{
      uuid: "link-uuid",
      mediaUuids: ["89b5a9bd-aae5-4c67-a4fe-a38c19a2c452"],
      access_token: "[REDACTED]",
    }],
  },
  rawJson: "{\"items\":[]}",
  error: null,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FanvueApiExplorerPage", () => {
  it("selects only allowlisted endpoints and renders diagnostics", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<FanvueApiExplorerPage />);
    expect(screen.getByText("Developer Tool — Read Only")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Endpoint"), { target: { value: "media-links" } });
    fireEvent.click(screen.getByRole("button", { name: "Run GET /media-links" }));
    await waitFor(() => expect(screen.getByText("/media-links")).toBeInTheDocument());
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/v1/developer/fanvue-api-explorer/media-links?",
      expect.objectContaining({ cache: "no-store", headers: expect.any(Headers) }),
    );
  });

  it("surfaces authentication and provider errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "OAuth required" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<FanvueApiExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Run GET /insights/earnings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("OAuth required");
  });

  it("marks successfully sorted earnings responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        ...responseBody,
        endpoint: "/insights/earnings",
        body: {
          data: [
            { id: "older", date: "2026-07-20T12:00:00Z" },
            { id: "newest", date: "2026-07-24T12:00:00Z" },
          ],
        },
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<FanvueApiExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Run GET /insights/earnings" }));
    expect(await screen.findByText("Sorted by newest transaction")).toBeInTheDocument();
  });

  it("populates the Media UUID dropdown from Media Links and executes the selected media request", async () => {
    const mediaUuid = "89b5a9bd-aae5-4c67-a4fe-a38c19a2c452";
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(responseBody), {
        status: 200,
        headers: { "content-type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...responseBody,
        endpoint: `/media/${mediaUuid}`,
        body: { uuid: mediaUuid, purchasedByFan: { username: "fan" } },
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }));
    render(<FanvueApiExplorerPage />);

    fireEvent.change(screen.getByLabelText("Endpoint"), { target: { value: "media-links" } });
    fireEvent.click(screen.getByRole("button", { name: "Run GET /media-links" }));
    await screen.findByText("/media-links");
    fireEvent.change(screen.getByLabelText("Endpoint"), { target: { value: "media" } });

    const selector = screen.getByLabelText("Media UUID");
    expect(selector).toHaveValue(mediaUuid);
    expect(screen.getByRole("option", { name: mediaUuid })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run GET /media/{uuid}" }));

    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
      `/api/v1/developer/fanvue-api-explorer/media?media_uuid=${mediaUuid}`,
      expect.objectContaining({ cache: "no-store", headers: expect.any(Headers) }),
    ));
  });

  it("executes GET /users/me through the allowlisted current-user operation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        ...responseBody,
        endpoint: "/users/me",
        body: { uuid: "creator-uuid", handle: "creator" },
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    render(<FanvueApiExplorerPage />);
    fireEvent.change(screen.getByLabelText("Endpoint"), { target: { value: "current-user" } });
    fireEvent.click(screen.getByRole("button", { name: "Run GET /users/me" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/developer/fanvue-api-explorer/current-user?",
      expect.objectContaining({ cache: "no-store", headers: expect.any(Headers) }),
    ));
  });
});

describe("FanvueJsonViewer", () => {
  it("renders collapsible highlighted JSON, searches, and copies redacted JSON", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<FanvueJsonViewer body={responseBody.body} rawJson={responseBody.rawJson} />);
    expect(screen.getByText("uuid")).toHaveClass("fanvue-json__key--highlight");
    expect(screen.getByText("mediaUuids")).toHaveClass("fanvue-json__key--highlight");
    expect(document.querySelector("details")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search JSON"), { target: { value: "link-uuid" } });
    expect(screen.getByText('"link-uuid"')).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy JSON" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining("[REDACTED]"),
    ));
  });
});
