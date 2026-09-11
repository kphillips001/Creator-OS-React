import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AvaConfigurationPage } from "./AvaConfigurationPage";

vi.mock("../creator-personality/CreatorPersonalityPage", () => ({ CreatorPersonalityPage: () => <div>Personality canonical editor</div> }));
vi.mock("../social-creative-direction/SocialCreativeDirectionPage", () => ({ SocialCreativeDirectionPage: () => <div>Creative canonical editor</div> }));
vi.mock("../creator-lifestyle/CreatorLifestylePage", () => ({ CreatorLifestylePage: () => <div>Lifestyle canonical editor</div> }));
vi.mock("../creator-world-model/CreatorWorldModelPage", () => ({ CreatorWorldModelPage: () => <div>World canonical editor</div> }));

describe("AvaConfigurationPage", () => {
  it("defaults to Personality and mounts only the selected independent editor", () => {
    render(<AvaConfigurationPage />);
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(screen.getByRole("tab", { name: "Identity & Personality" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Personality canonical editor")).toBeInTheDocument();
    expect(screen.queryByText("Creative canonical editor")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Creative Direction" }));
    expect(screen.getByText("Creative canonical editor")).toBeInTheDocument();
    expect(screen.queryByText("Personality canonical editor")).not.toBeInTheDocument();
  });

  it("explains World privacy authority without exposing a private location", () => {
    render(<AvaConfigurationPage />);
    fireEvent.click(screen.getByRole("tab", { name: "World & Continuity" }));
    expect(screen.getByText(/privacy-safe geography/i)).toBeInTheDocument();
    expect(screen.queryByText(/Wilmington/i)).not.toBeInTheDocument();
    expect(screen.getByText("World canonical editor")).toBeInTheDocument();
  });
});
