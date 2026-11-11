import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps a rendering bug from blanking the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("necto UI error", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center bg-slate-950 p-8">
          <div className="max-w-lg rounded-lg border border-rose-900/60 bg-rose-950/30 p-6 text-sm text-rose-100">
            <h1 className="text-base font-semibold">Something went wrong</h1>
            <p className="mt-2 break-words text-rose-200/80">{this.state.error.message}</p>
            <p className="mt-3 text-xs text-rose-300/60">
              Open the browser console for the stack, or reload to try again.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 rounded border border-rose-800 px-3 py-1.5 text-xs text-rose-100 transition-colors hover:bg-rose-900/40"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
