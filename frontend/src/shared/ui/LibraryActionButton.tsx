import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./shared-ui.css";

type LibraryActionButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  icon: LucideIcon;
  tooltip: string;
  label?: string;
  accent?: boolean;
};

export function LibraryActionButton({ icon: Icon, tooltip, label, accent = false, className = "", ...props }: LibraryActionButtonProps) {
  const classes = ["library-action-button", accent && "library-action-button--accent", label && "library-action-button--labeled", className].filter(Boolean).join(" ");
  return <button aria-label={tooltip} className={classes} title={tooltip} type="button" {...props}>
    <Icon aria-hidden="true" size={16} strokeWidth={2} />
    {label && <span>{label}</span>}
  </button>;
}

export function LibraryActionGroup({ children, label }: { children: ReactNode; label: string }) {
  return <div aria-label={label} className="library-action-group">{children}</div>;
}
