import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DeveloperAgentExecutionProvider,
} from "../../features/developer-agent/DeveloperAgentExecutionContext";
import { TopBar } from "./TopBar";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}:{JSON.stringify(location.state)}</output>;
}

afterEach(() => vi.restoreAllMocks());

describe("Developer Agent notifications", () => {
  it("opens a persisted completion notification and navigates back to its report", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/health")) return Promise.resolve(new Response(JSON.stringify({
        overallReadiness: "READY", reason: "Ready", persistenceAvailable: true,
      }), { status: 200 }));
      if (url.endsWith("/notifications")) return Promise.resolve(new Response(JSON.stringify({
        items: [{
          notification_id: "notification-1",
          execution_id: "execution-1",
          title: "Implementation completed.",
          detail: "Review required.",
          created_at: "2026-07-26T12:00:00Z",
          is_read: false,
        }],
      }), { status: 200 }));
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <DeveloperAgentExecutionProvider>
          <TopBar onMenuToggle={() => undefined} />
          <LocationProbe />
        </DeveloperAgentExecutionProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
    expect(screen.getByLabelText("Developer Agent notifications")).toHaveTextContent("Implementation completed.");
    fireEvent.click(screen.getByRole("button", { name: /Implementation completed/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("/home:");
    expect(screen.getByTestId("location")).toHaveTextContent("developerExecutionId");
  });
});
