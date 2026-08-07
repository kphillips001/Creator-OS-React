import {
  Bell,
  BriefcaseBusiness,
  ChevronDown,
  CircleUserRound,
  Command,
  Menu,
  Search,
  Waves,
  X,
} from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useDeveloperAgentExecutions } from "../../features/developer-agent/DeveloperAgentExecutionContext";
import { useBackgroundOperations } from "../../features/background-operations/BackgroundOperationsContext";
import type { BackgroundOperation } from "../../features/background-operations/BackgroundOperationsContext";
import { environment } from "../../infrastructure/config/environment";
import { allNavigationItems } from "../navigation/navigation";
import "./app-shell.css";

type TopBarProps = {
  onMenuToggle: () => void;
};

function elapsed(startedAt: string | null, completedAt: string | null) {
  const start = Date.parse(startedAt || "");
  if (!Number.isFinite(start)) return "Not started";
  const end = completedAt ? Date.parse(completedAt) : Date.now();
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function operationLabel(operation: BackgroundOperation) {
  if (operation.operationType === "content_studio_autonomous_inspiration") {
    return "Content Studio — Inspire Me";
  }
  if (operation.operationType === "photoshoot_generation") {
    const shot = Number(operation.metadata.shotNumber || 0);
    const target = Number(operation.metadata.targetShotCount || 0);
    return target === 0
      ? `Photoshoot Studio — Generating Shot ${shot} · Open-ended`
      : `Photoshoot Studio — Generating Shot ${shot} of ${target}`;
  }
  return operation.operationType.replaceAll("_", " ");
}

export function TopBar({ onMenuToggle }: TopBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);
  const { notifications, markRead } = useDeveloperAgentExecutions();
  const { active, recent, activeCount, cancel, retry } = useBackgroundOperations();
  const unread = notifications.filter((notification) => !notification.is_read).length;
  const currentItem = allNavigationItems.find(
    (item) => item.path === location.pathname,
  );

  return (
    <header className="topbar">
      <div className="topbar__context">
        <button
          className="topbar__menu-button"
          type="button"
          onClick={onMenuToggle}
          aria-label="Toggle navigation"
        >
          <Menu size={19} />
        </button>
        <div>
          <span>{environment.appName}</span>
          <strong>{currentItem?.label ?? "Creator_OS"}</strong>
        </div>
      </div>

      <div className="topbar__actions">
        <button className="topbar__search" type="button">
          <Search size={16} aria-hidden="true" />
          <span>Search Creator_OS</span>
          <kbd>
            <Command size={11} aria-hidden="true" /> K
          </kbd>
        </button>
        <div className="topbar__reserved" aria-label="Creative context">
          <div className="topbar__reserved-item">
            <CircleUserRound size={15} aria-hidden="true" />
            <span>
              <small>Creator</small>
              <strong>Not selected</strong>
            </span>
          </div>
          <div className="topbar__reserved-item">
            <BriefcaseBusiness size={15} aria-hidden="true" />
            <span>
              <small>Account</small>
              <strong>Not connected</strong>
            </span>
          </div>
          <button className="topbar__reserved-item topbar__reserved-item--jobs" type="button"
            aria-expanded={jobsOpen} onClick={() => setJobsOpen((current) => !current)}>
            <Waves size={15} aria-hidden="true" />
            <span>
              <small>Jobs</small>
              <strong>{activeCount ? `${activeCount} Active` : "Idle"}</strong>
            </span>
          </button>
        </div>
        {jobsOpen && <section className="topbar__jobs-panel" aria-label="Background Operations">
          <header><span><strong>Background Operations</strong><small>{activeCount} active</small></span>
            <button type="button" aria-label="Close Jobs" onClick={() => setJobsOpen(false)}><X size={15} /></button></header>
          <div className="topbar__jobs-list">
            {active.length === 0 && recent.length === 0 && <p>No background operations yet.</p>}
            {[...active, ...recent].slice(0, 12).map((operation) => <article key={operation.operationId}>
              <div><strong>{operationLabel(operation)}</strong><span>{operation.status}</span></div>
              <small>{operation.originatingWorkspace.replaceAll("_", " ")} · {operation.currentStage || "Queued"}</small>
              <p>{operation.errorMessage || operation.stageMessage || "Waiting for work"}</p>
              <time>{elapsed(operation.startedAt, operation.completedAt)}</time>
              {operation.progressTotal > 0 && <progress max={100} value={operation.progressPercent} />}
              <footer>
                {operation.resultLocation && <button type="button" onClick={() => {
                  setJobsOpen(false); navigate(operation.resultLocation!);
                }}>{operation.status === "SUCCEEDED" || operation.status === "PARTIAL" ? "Open Result" : "Return to Workspace"}</button>}
                {operation.cancellationSupported && active.includes(operation)
                  && <button type="button" onClick={() => void cancel(operation.operationId)}>Cancel</button>}
                {(operation.status === "FAILED" || operation.status === "CANCELLED")
                  && <button type="button" onClick={() => void retry(operation.operationId)}>Retry</button>}
              </footer>
            </article>)}
          </div>
        </section>}
        <div className="topbar__notifications">
          <button
            className="topbar__icon-button"
            type="button"
            aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
            aria-expanded={notificationsOpen}
            onClick={() => setNotificationsOpen((current) => !current)}
          >
            <Bell size={18} />
            {unread > 0 && <span className="topbar__notification-count">{unread}</span>}
          </button>
          {notificationsOpen && <section className="topbar__notification-panel" aria-label="Developer Agent notifications">
            <header><strong>Notifications</strong><span>{unread} unread</span></header>
            {!notifications.length
              ? <p>No Developer Agent notifications.</p>
              : notifications.map((notification) => <button key={notification.notification_id} onClick={() => {
                void markRead(notification.notification_id);
                setNotificationsOpen(false);
                navigate("/home", { state: { developerExecutionId: notification.execution_id } });
              }} type="button">
                <strong>{notification.title}</strong>
                <span>{notification.detail}</span>
                <time>{new Date(notification.created_at).toLocaleString()}</time>
              </button>)}
          </section>}
        </div>
        <button className="topbar__profile" type="button" aria-label="User menu">
          <span>CO</span>
          <ChevronDown size={13} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
