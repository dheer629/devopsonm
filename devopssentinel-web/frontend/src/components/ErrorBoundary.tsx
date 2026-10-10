import { AlertTriangle, RefreshCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  /** Shown in the heading, e.g. the route name. */
  label?: string;
}

interface State {
  error: Error | null;
}

/**
 * Route-level error isolation (spec section 131).
 *
 * A single component throwing must not blank the whole console. The shell,
 * scope selectors, palette and status bar stay mounted, so the operator keeps
 * their context and can navigate away or retry the failed region only.
 *
 * The message is shown verbatim rather than replaced with "something went
 * wrong" (spec section 335), and the stack is available behind Details.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Local diagnostic only -- nothing is transmitted anywhere (spec 212/213).
    console.error("DevOpsSentinel view error", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="m-3 space-y-2 rounded-md border border-critical/40 bg-critical/5 p-4"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-critical" aria-hidden="true" />
          <h2 className="text-[13px] font-semibold text-text">
            {this.props.label ? `${this.props.label} failed to render` : "This view failed to render"}
          </h2>
        </div>

        <p className="mono text-[12px] text-critical">{error.message}</p>

        <dl className="text-[12px] text-text-muted">
          <div>
            <dt className="inline font-medium text-text">Impact </dt>
            <dd className="inline">
              Only this view is affected. The rest of the console, your context and namespace are
              intact.
            </dd>
          </div>
          <div>
            <dt className="inline font-medium text-text">Next safe action </dt>
            <dd className="inline">
              Retry the view, or navigate elsewhere with the command palette (Ctrl K). No cluster
              write can result from this failure.
            </dd>
          </div>
        </dl>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={this.reset}>
            <RefreshCw className="h-3.5 w-3.5" /> Retry view
          </Button>
          <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
            Reload console
          </Button>
        </div>

        <details>
          <summary className="cursor-pointer text-[11.5px] text-text-muted">Technical details</summary>
          <pre className="mono mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-bg-elevated p-2 text-[11px] text-text-muted">
            {error.stack ?? error.message}
          </pre>
        </details>
      </div>
    );
  }
}
