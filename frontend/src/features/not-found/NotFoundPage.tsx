import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import "./not-found.css";

export function NotFoundPage() {
  return (
    <section className="not-found">
      <p>404 · Page unavailable</p>
      <h1>This Creator_OS route does not exist.</h1>
      <span>
        The requested page could not be found in Creator_OS.
      </span>
      <Link to="/library/generations">
        <ArrowLeft size={16} aria-hidden="true" />
        Return to Generation Library
      </Link>
    </section>
  );
}
