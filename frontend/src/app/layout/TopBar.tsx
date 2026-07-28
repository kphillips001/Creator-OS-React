import {
  Bell,
  BriefcaseBusiness,
  ChevronDown,
  CircleUserRound,
  Command,
  Menu,
  Search,
  Waves,
} from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useDeveloperAgentExecutions } from "../../features/developer-agent/DeveloperAgentExecutionContext";
import { environment } from "../../infrastructure/config/environment";
import { allNavigationItems } from "../navigation/navigation";
import "./app-shell.css";

type TopBarProps = {
  onMenuToggle: () => void;
};

export function TopBar({ onMenuToggle }: TopBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const { notifications, markRead } = useDeveloperAgentExecutions();
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
          <div className="topbar__reserved-item topbar__reserved-item--jobs">
            <Waves size={15} aria-hidden="true" />
            <span>
              <small>Jobs</small>
              <strong>Idle</strong>
            </span>
          </div>
        </div>
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
