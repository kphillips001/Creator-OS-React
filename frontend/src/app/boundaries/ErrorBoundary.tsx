import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

import "./error-boundary.css";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
};

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  public override state: ErrorBoundaryState = {
    hasError: false,
  };

  public static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  public override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Creator_OS interface error", error, info);
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <main className="error-boundary">
          <div className="error-boundary__panel">
            <AlertTriangle size={26} aria-hidden="true" />
            <p>Creator_OS interface</p>
            <h1>Creator_OS could not display this page.</h1>
            <span>
              Reload the application to try again. No production Creator_OS
              data has been changed.
            </span>
            <button type="button" onClick={() => window.location.reload()}>
              Reload application
            </button>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
