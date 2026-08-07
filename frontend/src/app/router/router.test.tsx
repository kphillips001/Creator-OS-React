import { matchRoutes } from "react-router-dom";
import { isValidElement } from "react";
import { describe, expect, it } from "vitest";
import { DeveloperNotesPage } from "../../features/developer-notes/DeveloperNotesPage";
import { PlaceholderPage } from "../../features/placeholder/PlaceholderPage";
import { router } from "./router";

describe("application route precedence", () => {
  it("resolves Developer Notes to its implemented page rather than a generated placeholder", () => {
    const matches = matchRoutes(router.routes, "/administration/developer-notes");
    const element = matches?.at(-1)?.route.element;
    expect(isValidElement(element)).toBe(true);
    if (!isValidElement(element)) throw new Error("Developer Notes route has no React element.");
    expect(element?.type).toBe(DeveloperNotesPage);
    expect(element?.type).not.toBe(PlaceholderPage);
  });
});
