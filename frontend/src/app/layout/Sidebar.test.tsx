import { render, screen } from "@testing-library/react";
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
    const administration = screen
      .getByRole("heading", { name: "Administration" })
      .closest("section");
    for (const label of [
      "Personality",
      "Social Creative Direction",
      "Lifestyle",
      "World Model",
    ]) {
      expect(administration).toContainElement(
        screen.getByRole("link", { name: label }),
      );
    }
    expect(
      screen.queryByRole("link", { name: "Story Studio" }),
    ).not.toBeInTheDocument();
    const headings = screen
      .getAllByRole("heading")
      .map((heading) => heading.textContent);
    expect(headings.indexOf("Administration")).toBeLessThan(
      headings.indexOf("Tools"),
    );
    expect(headings.indexOf("Tools")).toBeLessThan(headings.indexOf("System"));
    expect(
      screen.queryByRole("link", { name: "X Scraper" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "X Competitor Intelligence" }),
    ).toHaveAttribute("href", "/tools/x-intelligence");
    expect(screen.getByRole("link", { name: "Video Studio" })).toHaveClass(
      "sidebar__link--active",
    );
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
