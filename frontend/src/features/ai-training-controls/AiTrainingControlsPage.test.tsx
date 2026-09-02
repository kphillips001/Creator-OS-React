import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AiTrainingControlsPage } from "./AiTrainingControlsPage";

const response = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => value }) as Response;

describe("AiTrainingControlsPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("previews eligible text before activation and reloads the global inventory", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/preview")) return response({ originalOperatorText: "Keep replies concise", normalizedInstruction: "Keep replies concise", instructionType: "CONVERSATION_RULE", classification: "CONVERSATION_RULE", classificationReason: "Eligible as global conversational guidance.", runtimeEligible: true });
      if (init?.method === "POST") return response({ instructionId: "one", instructionType: "CONVERSATION_RULE", originalOperatorText: "Keep replies concise", normalizedInstruction: "Keep replies concise", status: "ENABLED", priority: 100, classificationReason: "Eligible", version: 1, createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-24T00:00:00Z", enabledAt: "2026-08-24T00:00:00Z", disabledAt: null, archivedAt: null }, 201);
      return response({ items: [] });
    });
    render(<AiTrainingControlsPage />);
    await screen.findByText("No active instructions.");
    fireEvent.click(screen.getByRole("button", { name: "+ New Global Training" }));
    fireEvent.change(screen.getByLabelText("Instruction"), { target: { value: "Keep replies concise" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview Instruction" }));
    expect(await screen.findByText("GPT conversation context", { selector: "dd" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("ai-training-controls") && init?.method === "POST")).toBe(true));
  });

  it("offers review storage instead of activation for backend-enforced rules", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).endsWith("/preview")
      ? response({ originalOperatorText: "Always sell", normalizedInstruction: "Always sell", instructionType: "SALES_RULE", classification: "REQUIRES_IMPLEMENTATION", classificationReason: "Requires CustomerSalesBrain.", runtimeEligible: false })
      : response({ items: [] }));
    render(<AiTrainingControlsPage />); await screen.findByText("No active instructions.");
    fireEvent.click(screen.getByRole("button", { name: "+ New Global Training" }));
    fireEvent.change(screen.getByLabelText("Instruction"), { target: { value: "Always sell" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview Instruction" }));
    expect(await screen.findByRole("button", { name: "Save for Review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
  });

  it("previews the supported adaptive readiness sales rule as backend enforced", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).endsWith("/preview")
      ? response({ originalOperatorText: "Build rapport before proactively selling", normalizedInstruction: "Adaptive Sales Readiness", instructionType: "SALES_RULE", policyKey: "ADAPTIVE_SALES_READINESS", enforcementMode: "BACKEND", classification: "SALES_RULE", classificationReason: "Customer Sales Brain policy", runtimeEligible: true, policyConfiguration: { normal_prospect_target_min: 10, normal_prospect_target_max: 15, meaningful_inactivity_days: 7, benchmark_never_forces_offer: true } })
      : response({ items: [] }));
    render(<AiTrainingControlsPage />); await screen.findByText("No active instructions.");
    fireEvent.click(screen.getByRole("button", { name: "+ New Global Training" }));
    fireEvent.change(screen.getByLabelText("Instruction"), { target: { value: "Build rapport before proactively selling" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview Instruction" }));
    expect(await screen.findByRole("heading", { name: "Adaptive Sales Readiness" })).toBeInTheDocument();
    expect(screen.getByText(/Automatic offer at maximum: NO/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate" })).toBeInTheDocument();
  });

  it("previews, persists, confirms, and displays a supported backend hard stop", async () => {
    let items: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/preview")) return response({ originalOperatorText: "If a customer is underage, stop chatting with that customer", normalizedInstruction: "Underage Customer Hard Stop", instructionType: "SAFETY_HARD_STOP", policyKey: "UNDERAGE_CUSTOMER", enforcementMode: "BACKEND", classification: "SAFETY_HARD_STOP", classificationReason: "Only UNDERAGE_BLOCKED customers are affected; other customers are unaffected. This does not mark age.", runtimeEligible: true });
      if (init?.method === "POST") {
        const created = { instructionId: "safety-one", instructionType: "SAFETY_HARD_STOP", policyKey: "UNDERAGE_CUSTOMER", enforcementMode: "BACKEND", originalOperatorText: "If a customer is underage, stop chatting with that customer", normalizedInstruction: "Underage Customer Hard Stop", status: "ENABLED", priority: 100, classificationReason: "Backend", version: 1, createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-24T00:00:00Z", enabledAt: "2026-08-24T00:00:00Z", disabledAt: null, archivedAt: null, runtimeRecognized: true };
        items = [created]; return response(created, 201);
      }
      return response({ items });
    });
    render(<AiTrainingControlsPage />); await screen.findByText("No active instructions.");
    fireEvent.click(screen.getByRole("button", { name: "+ New Global Training" }));
    fireEvent.change(screen.getByLabelText("Instruction"), { target: { value: "If a customer is underage, stop chatting with that customer" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview Instruction" }));
    expect(await screen.findByText("Backend enforced", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Unaffected.")).toBeInTheDocument();
    expect(screen.getByText(/does not automatically determine or mark customers underage/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Training Activated");
    expect(await screen.findByText("BACKEND ENFORCED")).toBeInTheDocument();
    expect(screen.getByText("GLOBAL POLICY")).toBeInTheDocument();
    expect(screen.getByText("ENABLED")).toBeInTheDocument();
  });

  it("does not confirm or close when backend activation fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/preview")) return response({ originalOperatorText: "underage stop chatting", normalizedInstruction: "Underage Customer Hard Stop", instructionType: "SAFETY_HARD_STOP", policyKey: "UNDERAGE_CUSTOMER", enforcementMode: "BACKEND", classification: "SAFETY_HARD_STOP", classificationReason: "Backend", runtimeEligible: true });
      if (init?.method === "POST") return response({ detail: "Persistence failed" }, 500);
      return response({ items: [] });
    });
    render(<AiTrainingControlsPage />); await screen.findByText("No active instructions.");
    fireEvent.click(screen.getByRole("button", { name: "+ New Global Training" }));
    fireEvent.change(screen.getByLabelText("Instruction"), { target: { value: "underage stop chatting" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview Instruction" }));
    fireEvent.click(await screen.findByRole("button", { name: "Activate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Persistence failed");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
