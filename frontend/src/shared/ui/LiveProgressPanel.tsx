import type { ReactNode } from "react";

import "./shared-ui.css";

export type LiveProgressTone = "active" | "waiting" | "paused" | "failed" | "complete";

type Props = {
  title: string;
  progressLabel: string;
  progressPercent: number;
  status: string;
  tone: LiveProgressTone;
  active?: boolean;
  children?: ReactNode;
  actions?: ReactNode;
};

export function LiveProgressPanel({
  title, progressLabel, progressPercent, status, tone, active = false, children, actions,
}: Props) {
  const value = Math.max(0, Math.min(100, progressPercent));
  return (
    <div className={`live-progress live-progress--${tone}`}>
      <header><h2>{title}</h2><strong>{progressLabel}</strong></header>
      <div className="live-progress__bar-row">
        <progress aria-label={`${title} progress`} max={100} value={value} />
        <strong>{Math.round(value)}%</strong>
      </div>
      {children}
      <div className="live-progress__status" role="status">
        {active && <span className="creator-os-spinner" aria-label="Active work" role="img" />}
        <span><small>Runtime Status</small><strong>{status}</strong></span>
      </div>
      {actions && <div className="live-progress__actions">{actions}</div>}
    </div>
  );
}
