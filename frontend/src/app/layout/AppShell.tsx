import { useState } from "react";
import { Outlet } from "react-router-dom";

import { DeveloperAgentExecutionProvider } from "../../features/developer-agent/DeveloperAgentExecutionContext";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import "./app-shell.css";

export function AppShell() {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <DeveloperAgentExecutionProvider><div
      className={`app-shell${
        isSidebarCollapsed ? " app-shell--sidebar-collapsed" : ""
      }`}
    >
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        isOpen={isSidebarOpen}
        onCollapseToggle={() =>
          setSidebarCollapsed((isCollapsed) => !isCollapsed)
        }
        onNavigate={() => setSidebarOpen(false)}
      />
      <button
        className={`app-shell__backdrop${
          isSidebarOpen ? " app-shell__backdrop--visible" : ""
        }`}
        type="button"
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />
      <div className="app-shell__stage">
        <TopBar onMenuToggle={() => setSidebarOpen((current) => !current)} />
        <main className="app-shell__workspace">
          <Outlet />
        </main>
      </div>
    </div></DeveloperAgentExecutionProvider>
  );
}
