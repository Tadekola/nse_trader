/**
 * Global Error Boundary
 * 
 * Catches unhandled errors and displays a recovery UI.
 * Logs errors in development for debugging.
 */

import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    
    // Log error in development
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary] Caught error:', error);
      console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
    }
    
    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-[var(--color-bg-primary)] flex items-center justify-center p-4">
          <div className="max-w-md w-full">
            <div className="card p-6 text-center">
              <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-500/10 flex items-center justify-center">
                <svg 
                  className="w-6 h-6 text-red-400" 
                  fill="none" 
                  stroke="currentColor" 
                  viewBox="0 0 24 24"
                >
                  <path 
                    strokeLinecap="round" 
                    strokeLinejoin="round" 
                    strokeWidth={2} 
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" 
                  />
                </svg>
              </div>
              
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
                Something went wrong
              </h2>
              
              <p className="text-sm text-[var(--color-text-secondary)] mb-4">
                An unexpected error occurred. Please try again or refresh the page.
              </p>
              
              {import.meta.env.DEV && this.state.error && (
                <div className="mb-4 p-3 bg-[var(--color-bg-tertiary)] rounded-lg text-left">
                  <p className="text-xs font-mono text-red-400 break-all">
                    {this.state.error.toString()}
                  </p>
                </div>
              )}
              
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={this.handleReset}
                  className="px-4 py-2 bg-[var(--color-accent-primary)] text-white text-sm font-medium rounded-lg hover:bg-[var(--color-accent-primary)]/90 transition-colors"
                >
                  Try Again
                </button>
                <button
                  onClick={() => window.location.reload()}
                  className="px-4 py-2 bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] text-sm font-medium rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors"
                >
                  Refresh Page
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
