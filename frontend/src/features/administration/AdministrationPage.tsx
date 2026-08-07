import { Activity, BookOpen, Bot, KeyRound, RadioTower, ShieldCheck, Webhook } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./administration.css";

const cards = [
  ["Developer Notes", "Review architectural decisions, migrations, and long-term initiatives.", "/administration/developer-notes", BookOpen],
  ["Provider Connections", "Connect and inspect external provider authentication.", "/administration/providers", RadioTower],
  ["OAuth Accounts", "Review account-scoped OAuth installations.", "/administration/oauth-accounts", ShieldCheck],
  ["Webhooks", "Configure provider event destinations.", "/administration/webhooks", Webhook],
  ["API Credentials", "Review application credential readiness.", "/administration/api-credentials", KeyRound],
  ["Publication Workers", "Inspect publication execution configuration.", "/administration/publication-workers", Bot],
  ["System Status", "Review administration health and readiness.", "/administration/system-status", Activity],
] as const;

export function AdministrationPage() {
  return <section className="administration-page">
    <PageHeader title="Administration" description="Operational configuration, provider authentication, and system readiness." />
    <div className="administration-grid">
      {cards.map(([title, description, path, Icon]) => <Link className="administration-card" key={title} to={path}>
        <Icon aria-hidden="true" size={22} /><div><h2>{title}</h2><p>{description}</p></div>
      </Link>)}
    </div>
  </section>;
}
