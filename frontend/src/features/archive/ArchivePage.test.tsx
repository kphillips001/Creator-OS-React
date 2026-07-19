import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ArchivePage } from "./ArchivePage";

describe("ArchivePage", () => {
  it("renders both history destinations", () => {
    render(<MemoryRouter><ArchivePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Archive" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Edited Content" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Published Content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Edited Content" })).toHaveAttribute("href", "/system/archive/edited");
    expect(screen.getByRole("link", { name: "Open Published Content" })).toHaveAttribute("href", "/system/archive/published");
    expect(screen.getByRole("link", { name: "Open Removed Content" })).toHaveAttribute("href", "/system/archive/removed");
  });

  it("opens the edited and published routes without duplicating their implementations", () => {
    const { unmount } = render(<MemoryRouter initialEntries={["/system/archive"]}><Routes><Route path="/system/archive" element={<ArchivePage />} /><Route path="/system/archive/edited" element={<div>Existing VersionHistoryPage</div>} /></Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("link", { name: "Open Edited Content" }));
    expect(screen.getByText("Existing VersionHistoryPage")).toBeInTheDocument();
    unmount();
    render(<MemoryRouter initialEntries={["/system/archive"]}><Routes><Route path="/system/archive" element={<ArchivePage />} /><Route path="/system/archive/published" element={<div>Existing PostedContentPage</div>} /></Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("link", { name: "Open Published Content" }));
    expect(screen.getByText("Existing PostedContentPage")).toBeInTheDocument();
  });
});
