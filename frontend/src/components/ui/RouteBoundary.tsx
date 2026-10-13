import { Component, Suspense, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { Button } from './Button';
import { Skeleton } from './Skeleton';

class RouteError extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <section className="page-container" role="alert"><h1 className="page-title">This page couldn’t open</h1><p className="page-description">Check your connection, then reload to open the latest version of Mentra.</p><Button variant="secondary" onClick={() => window.location.reload()}>Reload page</Button></section> : this.props.children;
  }
}
export function RouteBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <RouteError key={pathname === '/' || pathname.startsWith('/chat/') ? 'chat' : pathname}><Suspense fallback={<div className="page-container" aria-label="Loading page"><Skeleton variant="form" rows={3} /></div>}>{children}</Suspense></RouteError>;
}
