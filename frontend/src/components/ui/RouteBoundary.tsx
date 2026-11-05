import { Button } from './Button';
import { Skeleton } from './Skeleton';

export function RouteLoadError() {
  return <section className="page-container" role="alert">
    <h1 className="page-title">This page couldn’t open</h1>
    <p className="page-description">Check your connection, then reload to open the latest version of Mentra.</p>
    <Button variant="secondary" onClick={() => window.location.reload()}>Reload page</Button>
  </section>;
}

export function RouteLoading() {
  return <main className="page-container" aria-label="Loading page"><Skeleton variant="form" rows={3} /></main>;
}
