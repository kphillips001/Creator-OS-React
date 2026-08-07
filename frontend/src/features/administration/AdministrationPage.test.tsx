import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AdministrationPage } from "./AdministrationPage";

describe("AdministrationPage", () => {
  it("renders the administration capabilities and provider route", () => {
    render(<MemoryRouter><AdministrationPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Administration" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Provider Connections/ })).toHaveAttribute(
      "href", "/administration/providers");
    expect(screen.getByRole("link", { name: /Developer Notes/ })).toHaveAttribute(
      "href", "/administration/developer-notes");
    for (const title of ["OAuth Accounts", "Webhooks", "API Credentials", "Publication Workers", "System Status"]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });
});
