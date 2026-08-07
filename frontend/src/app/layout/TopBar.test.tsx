import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DeveloperAgentExecutionProvider,
} from "../../features/developer-agent/DeveloperAgentExecutionContext";
import { TopBar } from "./TopBar";
import { BackgroundOperationsProvider } from "../../features/background-operations/BackgroundOperationsContext";

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

describe("Background Operations Jobs indicator", () => {
  it("shows the active count and operation details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/background-operations")) return Promise.resolve(new Response(JSON.stringify({
        success: true,
        operations: url.includes("status=active") ? [{
          operationId: "operation-1", operationType: "content_studio_autonomous_inspiration",
          originatingWorkspace: "content_studio", subjectType: "creator_profile", subjectId: "1",
          status: "RUNNING", progressCurrent: 1, progressTotal: 3, progressPercent: 33,
          currentStage: "GENERATING", stageMessage: "Generating image 2", createdAt: "2026-08-05T12:00:00Z",
          startedAt: "2026-08-05T12:00:01Z", completedAt: null, resultLocation: "/studio/content",
          resultReference: "job-1", errorCode: null, errorMessage: null,
          cancellationSupported: false, metadata: {},
        }] : [],
      }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    });
    render(<MemoryRouter><DeveloperAgentExecutionProvider><BackgroundOperationsProvider pollMilliseconds={60_000}>
      <TopBar onMenuToggle={() => undefined} />
    </BackgroundOperationsProvider></DeveloperAgentExecutionProvider></MemoryRouter>);
    fireEvent.click(await screen.findByText("1 Active"));
    expect(screen.getByLabelText("Background Operations")).toHaveTextContent("Generating image 2");
    expect(screen.getByLabelText("Background Operations")).toHaveTextContent("Content Studio — Inspire Me");
  });

  it("labels an open-ended Photoshoot operation and returns to Photoshoot Studio", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/background-operations")) return Promise.resolve(new Response(JSON.stringify({
        success: true,
        operations: url.includes("status=active") ? [{
          operationId: "photoshoot-operation", operationType: "photoshoot_generation",
          originatingWorkspace: "photoshoot_studio", subjectType: "photoshoot_session", subjectId: "session-1",
          status: "RUNNING", progressCurrent: 0, progressTotal: 1, progressPercent: 42,
          currentStage: "GENERATING", stageMessage: "Generating image", createdAt: "2026-08-05T12:00:00Z",
          startedAt: "2026-08-05T12:00:01Z", completedAt: null, resultLocation: "/content/photoshoot",
          resultReference: "job-1", errorCode: null, errorMessage: null,
          cancellationSupported: false, metadata: { shotNumber: 4, targetShotCount: 0, openEnded: true },
        }] : [],
      }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    });
    render(<MemoryRouter initialEntries={["/home"]}><DeveloperAgentExecutionProvider><BackgroundOperationsProvider pollMilliseconds={60_000}>
      <TopBar onMenuToggle={() => undefined} /><LocationProbe />
    </BackgroundOperationsProvider></DeveloperAgentExecutionProvider></MemoryRouter>);
    fireEvent.click(await screen.findByText("1 Active"));
    expect(screen.getByLabelText("Background Operations")).toHaveTextContent(
      "Photoshoot Studio — Generating Shot 4 · Open-ended",
    );
    fireEvent.click(screen.getByRole("button", { name: "Return to Workspace" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/content/photoshoot");
  });
});
