import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { ErrorBoundary } from "./app/boundaries/ErrorBoundary";
import { router } from "./app/router/router";
import "./styles/global.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Creator_OS root element was not found.");
}

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  </StrictMode>,
);
