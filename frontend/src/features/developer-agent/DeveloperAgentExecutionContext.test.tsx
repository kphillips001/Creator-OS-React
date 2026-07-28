import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DeveloperAgentExecutionProvider,
  useDeveloperAgentExecutions,
} from "./DeveloperAgentExecutionContext";

function Harness() {
  const {
    readiness, notifications, recentExecutions, dispatchTask,
  } = useDeveloperAgentExecutions();
  return <div>
    <span>{readiness?.overallReadiness ?? "Checking"}</span>
    <span>{notifications[0]?.title ?? "No notifications"}</span>
    <span>{recentExecutions[0]?.issue_identifier ?? "No history"}</span>
    <button onClick={() => void dispatchTask("Database", "Package", "Task")} type="button">Send</button>
  </div>;
}

afterEach(() => vi.restoreAllMocks());

describe("Developer Agent backend client", () => {
  it("loads readiness, notifications, history, and immediately dispatches", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/health")) return Promise.resolve(new Response(JSON.stringify({
        overallReadiness: "READY", reason: "Ready", persistenceAvailable: true,
      }), { status: 200 }));
      if (url.endsWith("/notifications")) return Promise.resolve(new Response(JSON.stringify({
        items: [{ notification_id: "n1", title: "Review required.", is_read: false }],
      }), { status: 200 }));
      if (url.includes("/history?")) return Promise.resolve(new Response(JSON.stringify({
        items: [{ execution_id: "execution-1", issue_identifier: "Database" }],
      }), { status: 200 }));
      if (url.endsWith("/tasks/dispatch")) return Promise.resolve(new Response(JSON.stringify({
        task: { task_id: "task-1", status: "APPROVED" },
        execution: { execution_id: "execution-1", status: "QUEUED" },
      }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ task_id: "task-1" }), { status: 200 }));
    });
    render(<DeveloperAgentExecutionProvider><Harness /></DeveloperAgentExecutionProvider>);
    expect(await screen.findByText("READY")).toBeInTheDocument();
    expect(await screen.findByText("Review required.")).toBeInTheDocument();
    expect(await screen.findByText("Database")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/developer-agent/tasks/dispatch",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"require_manual_approval":false'),
      }),
    ));
  });
});
