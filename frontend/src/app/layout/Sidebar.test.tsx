import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

describe("Sidebar navigation organization", () => {
  it("renders Studios and Libraries and preserves active-route highlighting", () => {
    render(
      <MemoryRouter initialEntries={["/studio/video"]}>
        <Sidebar
          isCollapsed={false}
          isOpen
          onCollapseToggle={vi.fn()}
          onNavigate={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Studios" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Libraries" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Content Creation" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Creator" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading")[0]).toHaveTextContent("Studios");
    expect(screen.getByRole("button", { name: "Administration" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Ava Configuration" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Story Studio" }),
    ).not.toBeInTheDocument();
    const sections = [...screen.getByRole("navigation", { name: "Primary navigation" }).querySelectorAll(":scope > section")];
    expect(sections.at(-4)?.querySelector("h2")?.textContent).toBe("Tools");
    expect(sections.at(-3)?.querySelector("button")?.textContent).toContain("Training");
    expect(sections.at(-2)?.querySelector("button")?.textContent).toContain("Administration");
    expect(sections.at(-1)?.querySelector("button")?.textContent).toContain("Developer Tools");
    expect(screen.getByRole("button", { name: "Developer Tools" })).toHaveAttribute(
      "aria-expanded", "false",
    );
    expect(screen.queryByRole("link", { name: "Test Chat" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "X Scraper" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "X Competitor Intelligence" }),
    ).toHaveAttribute("href", "/tools/x-intelligence");
    expect(screen.queryByRole("heading", { name: "System" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "IG Competitor Intelligence" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Archive" })).toHaveAttribute("href", "/system/archive");
    expect(screen.getByRole("link", { name: "Video Studio" })).toHaveClass(
      "sidebar__link--active",
    );
  });

  it("keeps Training compact and auto-expands for its active route", () => {
    const view = render(<MemoryRouter initialEntries={["/home"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    const toggle = screen.getByRole("button", { name: "Training" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "AI Training" })).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByRole("link", { name: "AI Training" })).toHaveAttribute("href", "/training/ai-training");
    view.unmount();
    render(<MemoryRouter initialEntries={["/training/ai-training?tab=history"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Training" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "AI Training" })).toHaveClass("sidebar__link--active");
  });

  it("keeps Developer Tools last, collapsed by default, and toggles all ten tools", () => {
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} />
      </MemoryRouter>,
    );
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    const groups = navigation.querySelectorAll(":scope > section");
    const developerGroup = groups[groups.length - 1];
    if (!developerGroup) throw new Error("Developer Tools group was not rendered.");
    expect(developerGroup).toHaveClass("sidebar__group--developer");
    const toggle = screen.getByRole("button", { name: "Developer Tools" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(developerGroup.querySelectorAll("a")).toHaveLength(11);
    for (const label of [
      "Operations", "Test Chat", "Commerce Learning", "Recommendation Diagnostics",
      "Commerce Sales Explorer", "Fanvue API Explorer", "Fanvue Webhook Monitor",
      "Customer Commerce", "Purchase Intents", "Customer Sales Brain",
      "Commercial Offering Selector",
    ]) expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Test Chat" })).not.toBeInTheDocument();
    expect(screen.getByText("Shell online")).toBeInTheDocument();
  });

  it("automatically expands Developer Tools and preserves child active styling", () => {
    render(
      <MemoryRouter initialEntries={["/developer/test-chat"]}>
        <Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Developer Tools" })).toHaveAttribute(
      "aria-expanded", "true",
    );
    expect(screen.getByRole("link", { name: "Test Chat" })).toHaveClass(
      "sidebar__link--active",
    );
  });

  it("expands Administration independently and shows exactly four compact children", () => {
    render(<MemoryRouter initialEntries={["/home"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    const toggle = screen.getByRole("button", { name: "Administration" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    for (const label of ["Ava Configuration", "Ava Rules", "Provider Connections", "Developer Notes"])
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Personality" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Developer Tools" })).toHaveAttribute("aria-expanded", "false");
  });

  it("automatically expands Administration for an active child", () => {
    render(<MemoryRouter initialEntries={["/agents/ai-training"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Administration" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Ava Rules" })).toHaveClass("sidebar__link--active");
  });

  it("treats Operations as the first active Developer Tools child", () => {
    render(
      <MemoryRouter initialEntries={["/business/operations?tab=failures"]}>
        <Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("heading", { name: "Advanced" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Developer Tools" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const operations = screen.getByRole("link", { name: "Operations" });
    expect(operations).toHaveAttribute("href", "/business/operations");
    expect(operations).toHaveClass("sidebar__link--active");
    expect(operations.parentElement?.querySelector("a")).toBe(operations);
  });

  it("uses the normal active state for X Competitor Intelligence", () => {
    render(
      <MemoryRouter initialEntries={["/tools/x-intelligence"]}>
        <Sidebar
          isCollapsed={false}
          isOpen
          onCollapseToggle={vi.fn()}
          onNavigate={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("link", { name: "X Competitor Intelligence" }),
    ).toHaveClass("sidebar__link--active");
    expect(
      screen.queryByRole("link", { name: "X Scraper" }),
    ).not.toBeInTheDocument();
  });

  it("highlights Archive under Business without activating hidden routes", () => {
    const view = render(<MemoryRouter initialEntries={["/system/archive"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Archive" })).toHaveClass("sidebar__link--active");
    view.unmount();
    render(<MemoryRouter initialEntries={["/diagnostics"]}><Sidebar isCollapsed={false} isOpen onCollapseToggle={vi.fn()} onNavigate={vi.fn()} /></MemoryRouter>);
    expect(screen.queryByRole("link", { name: "Archive" })).not.toHaveClass("sidebar__link--active");
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("keeps collapsed labels and behavior intact", () => {
    render(
      <MemoryRouter>
        <Sidebar
          isCollapsed
          isOpen={false}
          onCollapseToggle={vi.fn()}
          onNavigate={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("link", { name: "Content Studio" }),
    ).toHaveAttribute("title", "Content Studio");
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
  });
});
