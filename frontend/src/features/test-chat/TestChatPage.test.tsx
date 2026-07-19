import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TestChatPage } from "./TestChatPage";

const session = {
  session_id: "session-1",
  test_user: { name: "Test User", relationship: "warm", buyer_tier: "new_buyer" },
  messages: [],
  external_sends_disabled: true,
};

describe("TestChatPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads, sends a customer message, and displays the narrow decision summary", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        reply: "I can help with that.",
        intent: "high", relationship: "sales", sell: true,
        reason: "No eligible products", product: null, asset: null,
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);

    expect(await screen.findByText("new_buyer")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "What can I buy?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findAllByText("I can help with that.")).toHaveLength(2);
    expect(screen.getByText("No eligible products")).toBeInTheDocument();
    expect(screen.getByText("YES")).toBeInTheDocument();
    expect(screen.getAllByText("None").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("🚫 External Sends Disabled")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/developer/test-chat/turns",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("shows developer-only engine diagnostics in a collapsible error card", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: {
        exception_type: "RuntimeError", exception_message: "OpenAI API key is not configured.",
        file: "C:/Creator-OS-React/app/main.py", line_number: "54",
        stack_trace: "Traceback…", root_cause: "Missing OpenAI configuration",
      } }), { status: 502 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("new_buyer");
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Sales Agent Error")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();
    expect(screen.getByText("OpenAI API key is not configured.")).toBeInTheDocument();
    expect(screen.getByText("Stack trace")).toBeInTheDocument();
  });
});
