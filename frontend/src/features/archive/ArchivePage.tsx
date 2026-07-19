import { Images, Trash2, Upload } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../shared/ui/PageHeader";
import "./archive.css";

const destinations = [
  {
    title: "Edited Content",
    description: "View previous approved versions of Generation Library assets.",
    button: "Open Edited Content",
    path: "/system/archive/edited",
    icon: Images,
  },
  {
    title: "Published Content",
    description: "Browse media previously published to X, Telegram, Fanvue, and future platforms.",
    button: "Open Published Content",
    path: "/system/archive/published",
    icon: Upload,
  },
  {
    title: "Removed Content",
    description: "Restore removed Generation Library assets or delete them permanently.",
    button: "Open Removed Content",
    path: "/system/archive/removed",
    icon: Trash2,
  },
] as const;

export function ArchivePage() {
  return (
    <section className="archive-page">
      <PageHeader title="Archive" description="Browse Creator_OS history and previously published content." />
      <div className="archive-page__cards">
        {destinations.map((destination) => {
          const Icon = destination.icon;
          return <article className="archive-page__card" key={destination.path}><Icon aria-hidden="true" size={30} /><h2>{destination.title}</h2><p>{destination.description}</p><Link to={destination.path}>{destination.button}</Link></article>;
        })}
      </div>
    </section>
  );
}
