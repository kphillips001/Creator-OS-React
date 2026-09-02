import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiTrainingPage } from "./AiTrainingPage";
import type { AiTrainingNote } from "../../infrastructure/api/aiTrainingApi";

const response = (value: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => value,
}) as Response;

const note = (overrides: Partial<AiTrainingNote> = {}): AiTrainingNote => ({
  id: "training-1",
  title: "Prefer concrete examples",
  details: "Show one good response and one bad response.",
  integrated: false,
  integratedAt: null,
  createdAt: "2026-08-20T12:00:00Z",
  updatedAt: "2026-08-20T12:00:00Z",
  subnotes: [{ id: "sub-1", todoId: "training-1", title: "Existing Note", content: "Show one good response and one bad response.", completed: false, createdAt: "2026-08-20T12:00:00Z", updatedAt: "2026-08-20T12:00:00Z" }],
  ...overrides,
});

describe("AiTrainingPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the independent empty state and creation action", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ items: [] }));
    render(<AiTrainingPage />);
    expect(await screen.findByRole("heading", { name: "AI Developer Notes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI DEVELOPMENT NOTES" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ New AI Developer Note" })).toBeInTheDocument();
    expect(await screen.findByText("No AI developer notes yet.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toMatch(/ai-training\/notes$/);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("developer-notes"))).toBe(false);
  });

  it("reuses the complete collapsed parent/subnote workflow with durable isolated actions", async () => {
    let items = [note(), note({ id: "training-2", title: "Older integrated rule", details: null, integrated: true, integratedAt: "2026-08-20T13:00:00Z", createdAt: "2026-08-19T12:00:00Z", subnotes: [] })];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      expect(url).toContain("/ai-training/notes");
      if (init?.method === "POST" && url.endsWith("/subnotes")) {
        const body = JSON.parse(String(init.body)) as { title: string; content: string };
        const parentId = decodeURIComponent(url.split("/").at(-2) || "");
        const created = { id: "sub-2", todoId: parentId, ...body, completed: false, createdAt: "2026-08-22T20:30:00Z", updatedAt: "2026-08-22T20:30:00Z" };
        items = items.map((item) => item.id === parentId ? { ...item, subnotes: [...item.subnotes, created] } : item);
        return response(created, 201);
      }
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { title: string; details: string };
        const created = note({ id: "training-3", title: body.title, details: body.details, createdAt: "2026-08-20T15:00:00Z", updatedAt: "2026-08-20T15:00:00Z", subnotes: [] });
        items = [...items, created];
        return response(created, 201);
      }
      if (init?.method === "PATCH" && url.includes("/subnotes/")) {
        const parts = url.split("/"); const subnotesIndex = parts.lastIndexOf("subnotes"); const parentId = decodeURIComponent(parts[subnotesIndex - 1] || ""); const subnoteId = decodeURIComponent(parts[subnotesIndex + 1] || "");
        const changes = JSON.parse(String(init.body)) as { title?: string; content?: string; completed?: boolean };
        let updated = items.find((item) => item.id === parentId)!.subnotes.find((value) => value.id === subnoteId)!;
        updated = { ...updated, ...changes, updatedAt: "2026-08-22T21:00:00Z" };
        items = items.map((item) => item.id === parentId ? { ...item, subnotes: item.subnotes.map((value) => value.id === subnoteId ? updated : value) } : item);
        return response(updated);
      }
      if (init?.method === "PATCH") {
        const id = decodeURIComponent(url.split("/").at(-1) || "");
        const changes = JSON.parse(String(init.body)) as { title?: string; integrated?: boolean; details?: string | null };
        const current = items.find((item) => item.id === id)!;
        const updated = { ...current, ...(changes.title === undefined ? {} : { title: changes.title }), ...(changes.integrated === undefined ? {} : { integrated: changes.integrated, integratedAt: changes.integrated ? "2026-08-20T16:00:00Z" : null }), ...(changes.details === undefined ? {} : { details: changes.details }) };
        items = items.map((item) => item.id === id ? updated : item);
        return response(updated);
      }
      if (init?.method === "DELETE" && url.includes("/subnotes/")) {
        const parts=url.split("/");const parentId=decodeURIComponent(parts.at(-3)!);const subnoteId=decodeURIComponent(parts.at(-1)!);items=items.map(item=>item.id===parentId?{...item,subnotes:item.subnotes.filter(value=>value.id!==subnoteId)}:item);return response(null,204);
      }
      if (init?.method === "DELETE") {
        const id = decodeURIComponent(url.split("/").at(-1) || "");
        items = items.filter((item) => item.id !== id);
        return response(null, 204);
      }
      return response({ items });
    });

    const view = render(<AiTrainingPage />);
    const firstToggle = await screen.findByRole("button", { name: "Toggle Prefer concrete examples" });
    expect(firstToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Show one good response and one bad response.")).not.toBeInTheDocument();
    expect(screen.getByText("Added Aug 20, 2026")).toBeInTheDocument();
    fireEvent.click(firstToggle);
    const childToggle=screen.getByRole("button",{name:"Toggle subnote Existing Note"});expect(childToggle).toHaveAttribute("aria-expanded","false");expect(screen.getByRole("button",{name:"Mark subnote Existing Note completed"})).toHaveTextContent("Added Aug 20, 2026");
    fireEvent.click(screen.getByRole("button",{name:"Edit subnote Existing Note"}));expect(childToggle).toHaveAttribute("aria-expanded","true");expect(screen.getByLabelText("Title for subnote Existing Note")).toHaveValue("Existing Note");expect(screen.getByLabelText("Notes for subnote Existing Note")).toHaveValue("Show one good response and one bad response.");
    fireEvent.change(screen.getByLabelText("Title for subnote Existing Note"),{target:{value:"Concrete examples"}});fireEvent.change(screen.getByLabelText("Notes for subnote Existing Note"),{target:{value:"Updated example details."}});fireEvent.click(within(childToggle.closest("li")!).getByRole("button",{name:"Save"}));await waitFor(()=>expect(screen.getByRole("button",{name:"Toggle subnote Concrete examples"})).toHaveAttribute("aria-expanded","false"));
    const completion=screen.getByRole("button",{name:"Mark subnote Concrete examples completed"});fireEvent.click(completion);await waitFor(()=>expect(completion.closest("li")).toHaveClass("developer-subnote--completed"));expect(screen.getByRole("checkbox",{name:"Mark Prefer concrete examples integrated"})).not.toBeChecked();
    fireEvent.click(screen.getByRole("button",{name:"+ Add Subnote"}));fireEvent.change(screen.getByLabelText("New subnote title for Prefer concrete examples"),{target:{value:"Second child"}});fireEvent.change(screen.getByLabelText("New subnote notes for Prefer concrete examples"),{target:{value:"Second details"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));expect(await screen.findByRole("button",{name:"Toggle subnote Second child"})).toHaveAttribute("aria-expanded","false");
    fireEvent.click(screen.getByRole("button",{name:"Edit Prefer concrete examples"}));fireEvent.change(screen.getByLabelText("Title for Prefer concrete examples"),{target:{value:"Renamed training note"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));expect(await screen.findByText("Renamed training note")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Toggle subnote Concrete examples"})).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([url]) => !String(url).match(/openai|provider|embedding/i))).toBe(true);

    view.unmount();
    render(<AiTrainingPage />);
    const refreshed=await screen.findByRole("button", { name: "Toggle Renamed training note" });expect(refreshed).toHaveAttribute("aria-expanded", "false");fireEvent.click(refreshed);expect(screen.getByRole("button",{name:"Toggle subnote Concrete examples"})).toHaveAttribute("aria-expanded","false");expect(screen.getByRole("button",{name:"Mark subnote Concrete examples active"})).toBeInTheDocument();expect(screen.getByRole("button",{name:"Toggle subnote Second child"})).toBeInTheDocument();
  });
});
