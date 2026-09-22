import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiBalancesPage, formatBalance } from "./ApiBalancesPage";

const payload = { checkedAt: "2026-09-15T12:00:00Z", cacheTtlSeconds: 3600, providers: [
  { provider: "WAVESPEED", displayName: "WaveSpeed", status: "AVAILABLE", balance: "12.5", currency: "USD", unit: "currency", authoritative: true, checkedAt: "2026-09-15T12:00:00Z", lastSuccessfulAt: "2026-09-15T12:00:00Z", errorCategory: null },
  { provider: "TWITTERAPI_IO", displayName: "TwitterAPI.io", status: "AVAILABLE", balance: "12345", currency: null, unit: "credits", authoritative: true, checkedAt: "2026-09-15T12:00:00Z", lastSuccessfulAt: "2026-09-15T12:00:00Z", errorCategory: null },
  { provider: "XAI", displayName: "xAI / Grok", status: "CREDENTIAL_REQUIRED", balance: null, currency: null, unit: null, authoritative: false, checkedAt: "2026-09-15T12:00:00Z", lastSuccessfulAt: null, errorCategory: "MANAGEMENT_CREDENTIAL_REQUIRED" },
  { provider: "OPENAI", displayName: "OpenAI", status: "NOT_SUPPORTED", balance: null, currency: null, unit: null, authoritative: false, checkedAt: "2026-09-15T12:00:00Z", lastSuccessfulAt: null, errorCategory: "BALANCE_ENDPOINT_NOT_SUPPORTED" },
] } as const;
afterEach(() => vi.unstubAllGlobals());
describe("ApiBalancesPage", () => {
  it("renders authoritative values and the intentional OpenAI external balance workflow", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
    render(<ApiBalancesPage />);
    expect(await screen.findByText("$12.50")).toBeInTheDocument();
    expect(screen.getByText("12,345 credits")).toBeInTheDocument();
    expect(screen.getAllByText("Balance unavailable")).toHaveLength(1);
    expect(screen.getByText("Credential required")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
    expect(screen.getByText("Click below to view balance")).toBeInTheDocument();
    const viewBalance = screen.getByRole("link", { name: "View Balance" });
    expect(viewBalance).toHaveAttribute("href", "https://platform.openai.com/settings/organization/billing/overview");
    expect(viewBalance).toHaveAttribute("target", "_blank");
    expect(viewBalance).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByText("This provider does not expose an authoritative remaining balance through the configured API.")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Uses" })).toHaveLength(4);
  });
  it("opens and closes the OpenAI uses modal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
    render(<ApiBalancesPage />); await screen.findByText("Click below to view balance");
    fireEvent.click(screen.getAllByRole("button", { name: "Uses" })[3]!);
    expect(screen.getByRole("dialog", { name: "OpenAI Uses" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close uses" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("forces refresh without changing providers that fail independently", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload }); vi.stubGlobal("fetch", fetchMock);
    render(<ApiBalancesPage />); await screen.findByText("$12.50");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/business/api-balances?refresh=true", expect.anything()));
  });
  it("does not invent a numeric balance", () => {
    expect(formatBalance({ ...payload.providers[0], authoritative: false })).toBe("Balance unavailable");
  });
});
