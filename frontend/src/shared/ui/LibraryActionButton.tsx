import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./shared-ui.css";

type LibraryActionButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  icon: LucideIcon;
  tooltip: string;
};

export function LibraryActionButton({ icon: Icon, tooltip, ...props }: LibraryActionButtonProps) {
  return <button aria-label={tooltip} className="library-action-button" title={tooltip} type="button" {...props}>
    <Icon aria-hidden="true" size={16} strokeWidth={2} />
  </button>;
}

export function LibraryActionGroup({ children, label }: { children: ReactNode; label: string }) {
  return <div aria-label={label} className="library-action-group">{children}</div>;
}
