import { ChevronLeft, ChevronRight } from "lucide-react";
import { NavLink } from "react-router-dom";

import {
  brandIcon as BrandIcon,
  navigationGroups,
} from "../navigation/navigation";
import "./app-shell.css";

type SidebarProps = {
  isCollapsed: boolean;
  isOpen: boolean;
  onCollapseToggle: () => void;
  onNavigate: () => void;
};

export function Sidebar({
  isCollapsed,
  isOpen,
  onCollapseToggle,
  onNavigate,
}: SidebarProps) {
  return (
    <aside
      className={`sidebar${isOpen ? " sidebar--open" : ""}${
        isCollapsed ? " sidebar--collapsed" : ""
      }`}
    >
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark" aria-hidden="true">
          <BrandIcon size={20} strokeWidth={1.8} />
        </span>
        <div className="sidebar__brand-copy">
          <strong>Creator_OS</strong>
          <span>Creative operating system</span>
        </div>
      </div>

      <nav className="sidebar__navigation" aria-label="Primary navigation">
        {navigationGroups.map((group) => (
          <section className="sidebar__group" key={group.label}>
            <h2>{group.label}</h2>
            <div className="sidebar__links">
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    aria-label={isCollapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      `sidebar__link${isActive ? " sidebar__link--active" : ""}`
                    }
                    key={item.path}
                    onClick={onNavigate}
                    title={isCollapsed ? item.label : undefined}
                    to={item.path}
                  >
                    <Icon size={18} strokeWidth={1.65} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          </section>
        ))}
      </nav>

      <div className="sidebar__footer">
        <div className="sidebar__footer-status">
          <span className="sidebar__footer-dot" aria-hidden="true" />
          <span>Shell online</span>
        </div>
        <button
          className="sidebar__collapse"
          type="button"
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onCollapseToggle}
        >
          {isCollapsed ? (
            <ChevronRight size={16} aria-hidden="true" />
          ) : (
            <ChevronLeft size={16} aria-hidden="true" />
          )}
        </button>
      </div>
    </aside>
  );
}
