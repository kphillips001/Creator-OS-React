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
import { useLocation } from "react-router-dom";

import { environment } from "../../infrastructure/config/environment";
import { allNavigationItems } from "../navigation/navigation";
import "./app-shell.css";

type TopBarProps = {
  onMenuToggle: () => void;
};

export function TopBar({ onMenuToggle }: TopBarProps) {
  const location = useLocation();
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
        <button
          className="topbar__icon-button"
          type="button"
          aria-label="Notifications"
        >
          <Bell size={18} />
        </button>
        <button className="topbar__profile" type="button" aria-label="User menu">
          <span>CO</span>
          <ChevronDown size={13} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
