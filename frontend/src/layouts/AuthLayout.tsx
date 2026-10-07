import { Outlet } from 'react-router-dom';
import mentraLogo from '../assets/mentra-logo.png';

export function AuthLayout() {
  return (
    <main className="flex min-h-dvh flex-col bg-background px-5 py-8 text-foreground sm:px-6 sm:py-12">
      <div className="flex flex-1 flex-col items-center justify-center">
        <div className="mb-8 flex items-center gap-3" aria-label="Mentra">
          <img alt="" aria-hidden="true" className="h-10 w-10 object-contain" src={mentraLogo} />
          <span className="text-xl font-semibold tracking-tight">mentra</span>
        </div>
        <div className="w-full max-w-md"><Outlet /></div>
        <p className="mt-8 text-xs text-subtle">A quieter way to learn.</p>
      </div>
    </main>
  );
}
