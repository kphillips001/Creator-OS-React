import { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

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
  const location = useLocation();
  const developerRoutes = navigationGroups.find(
    (group) => group.label === "Developer Tools",
  )?.items.map((item) => item.path) ?? [];
  const developerRouteActive = developerRoutes.includes(location.pathname);
  const administrationRoutes = navigationGroups.find(
    (group) => group.label === "Administration",
  )?.items.map((item) => item.path) ?? [];
  const administrationRouteActive = administrationRoutes.includes(location.pathname);
  const trainingRoutes = navigationGroups.find(
    (group) => group.label === "Training",
  )?.items.map((item) => item.path) ?? [];
  const trainingRouteActive = trainingRoutes.includes(location.pathname);
  const [developerToolsExpanded, setDeveloperToolsExpanded] = useState(
    developerRouteActive,
  );
  const [administrationExpanded, setAdministrationExpanded] = useState(
    administrationRouteActive,
  );
  const [trainingExpanded, setTrainingExpanded] = useState(trainingRouteActive);

  useEffect(() => {
    if (developerRouteActive) setDeveloperToolsExpanded(true);
  }, [developerRouteActive, location.pathname]);
  useEffect(() => {
    if (administrationRouteActive) setAdministrationExpanded(true);
  }, [administrationRouteActive, location.pathname]);
  useEffect(() => {
    if (trainingRouteActive) setTrainingExpanded(true);
  }, [trainingRouteActive, location.pathname]);

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
        {navigationGroups.map((group) => {
          const isDeveloperGroup = group.label === "Developer Tools";
          const isAdministrationGroup = group.label === "Administration";
          const isTrainingGroup = group.label === "Training";
          const isCompactGroup = isDeveloperGroup || isAdministrationGroup || isTrainingGroup;
          const expanded = isDeveloperGroup ? developerToolsExpanded : isAdministrationGroup ? administrationExpanded : trainingExpanded;
          const active = isDeveloperGroup ? developerRouteActive : isAdministrationGroup ? administrationRouteActive : trainingRouteActive;
          const showItems = !isCompactGroup || expanded;
          return (
          <section className={`sidebar__group${
            isCompactGroup ? " sidebar__group--developer" : ""
          }`} key={group.label}>
            {isCompactGroup ? (
              <button
                aria-expanded={expanded}
                aria-label={group.label}
                className={`sidebar__developer-toggle${
                  active ? " sidebar__developer-toggle--active" : ""
                }`}
                onClick={() => isDeveloperGroup
                  ? setDeveloperToolsExpanded((value) => !value)
                  : isAdministrationGroup
                    ? setAdministrationExpanded((value) => !value)
                    : setTrainingExpanded((value) => !value)}
                type="button"
              >
                <span>{group.label}</span>
                {expanded ? (
                  <ChevronDown size={13} aria-hidden="true" />
                ) : (
                  <ChevronRight size={13} aria-hidden="true" />
                )}
              </button>
            ) : <h2>{group.label}</h2>}
            {showItems && <div className="sidebar__links">
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
            </div>}
          </section>
          );
        })}
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
