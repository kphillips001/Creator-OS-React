import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProviderConnectionsPage } from "./ProviderConnectionsPage";

const response = (body: unknown, ok = true) => Promise.resolve({
  ok, json: () => Promise.resolve(body),
} as Response);
const status = {
  provider: "FANVUE", connected: true, connectionStatus: "CONNECTED",
  account: { id: 2, displayName: "Ava Blackthorne", username: "ava", fanvueUserUuid: "fanvue-1" },
  grantedScopes: ["read:creator", "write:creator", "read:media", "write:media"],
  requiredScopes: ["read:creator", "write:creator", "read:media", "write:media"],
  missingScopes: [], accessTokenExpiresAt: "2026-07-24T00:00:00Z",
  refreshTokenAvailable: true, lastSuccessfulRefresh: "2026-07-23T20:00:00Z",
  connectedAt: "2026-07-23T20:00:00Z", apiVersion: "2025-06-26",
  workerReady: false, publicationReady: true,
  mediaLinkCapability: { ready: true, reason: null },
};

afterEach(() => vi.unstubAllGlobals());

describe("ProviderConnectionsPage", () => {
  it("shows connected Fanvue status, scopes, and reconnect action", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(status)));
    render(<ProviderConnectionsPage />);
    expect(await screen.findByText("Ava Blackthorne · @ava")).toBeInTheDocument();
    expect(screen.getByText("write:creator")).toBeInTheDocument();
    expect(screen.getAllByText("Ready", { selector: "dd" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Reconnect Fanvue/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Refresh Status/ })).toBeInTheDocument();
  });

  it("shows a missing-scope reauthorization warning", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({
      ...status, connectionStatus: "REAUTHORIZATION_REQUIRED",
      grantedScopes: ["read:creator", "read:media", "write:media"],
      missingScopes: ["write:creator"], publicationReady: false,
      mediaLinkCapability: { ready: false, reason: "Missing write:creator" },
    })));
    render(<ProviderConnectionsPage />);
    expect(await screen.findByText("Reauthorization Required", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/Missing write:creator/)).toBeInTheDocument();
  });

  it("shows disconnected state and authorize action", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({
      ...status, connected: false, connectionStatus: "NOT_CONNECTED",
      grantedScopes: [], missingScopes: status.requiredScopes,
      refreshTokenAvailable: false, publicationReady: false,
      mediaLinkCapability: { ready: false, reason: "Fanvue is not connected." },
    })));
    render(<ProviderConnectionsPage />);
    expect(await screen.findByText("Not Connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Authorize Fanvue/ })).toBeInTheDocument();
  });

  it("refreshes provider status", async () => {
    const fetch = vi.fn(() => response(status));
    vi.stubGlobal("fetch", fetch);
    render(<ProviderConnectionsPage />);
    await screen.findByText("Ava Blackthorne · @ava");
    fireEvent.click(screen.getByRole("button", { name: /Refresh Status/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });
});
