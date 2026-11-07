import { createBrowserRouter, Navigate, useLocation } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { RouteLoading, RouteLoadError } from './components/ui/RouteBoundary';
import { AuthLayout } from './layouts/AuthLayout';
import { AuthProvider } from './components/auth/AuthProvider';
import { RequireAuth, RequireGuest } from './components/auth/AuthRoutes';
import { ChatSession } from './components/chat/ChatSession';
import { ProfileReady, RequireOnboardingComplete } from './components/student-profile/ProfileRoutes';
import { ProductMotion } from './components/ui/Motion';

function EventsRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set('tab', 'events');
  return <Navigate replace to={{ pathname: '/progress', search: params.toString() }} />;
}

const chat = {
  lazy: async () => ({ Component: (await import('./pages/ChatPage')).ChatPage }),
};

const router = createBrowserRouter([{
  HydrateFallback: RouteLoading,
  ErrorBoundary: RouteLoadError,
  children: [
    { Component: RequireGuest, children: [
      { Component: AuthLayout, children: [
        { path: 'login', lazy: async () => ({ Component: (await import('./pages/LoginPage')).LoginPage }) },
        { path: 'register', lazy: async () => ({ Component: (await import('./pages/RegisterPage')).RegisterPage }) },
      ] },
    ] },
    { Component: RequireAuth, children: [
      { Component: ProfileReady, children: [
        { path: 'onboarding', lazy: async () => ({ Component: (await import('./pages/OnboardingPage')).OnboardingPage }) },
        { path: 'calibration', lazy: async () => {
          const { OnboardingPage } = await import('./pages/OnboardingPage');
          return { Component: () => <OnboardingPage calibrationOnly /> };
        } },
        { Component: RequireOnboardingComplete, children: [
          { lazy: async () => ({ Component: (await import('./layouts/AppLayout')).AppLayout }), children: [{ ErrorBoundary: RouteLoadError, children: [
            { index: true, ...chat },
            { path: 'chat/:conversationId', ...chat },
            { path: 'library', lazy: async () => ({ Component: (await import('./pages/LibraryPage')).LibraryPage }) },
            { path: 'library/new', lazy: async () => ({ Component: (await import('./pages/AddMaterialPage')).AddMaterialPage }) },
            { path: 'library/:documentId', lazy: async () => ({ Component: (await import('./pages/MaterialDetailPage')).MaterialDetailPage }) },
            { path: 'progress', lazy: async () => ({ Component: (await import('./pages/ProgressPage')).ProgressPage }) },
            { path: 'assessments', lazy: async () => ({ Component: (await import('./pages/AssessmentsPage')).AssessmentsPage }) },
            { path: 'settings', lazy: async () => ({ Component: (await import('./pages/SettingsPage')).SettingsPage }) },
            { path: 'notifications', lazy: async () => ({ Component: (await import('./pages/NotificationsPage')).NotificationsPage }) },
            { path: 'events', Component: EventsRedirect },
            { path: '*', element: <Navigate replace to="/" /> },
          ] }] },
        ] },
      ] },
    ] },
  ],
}]);

export default function App() {
  return <ProductMotion><AuthProvider>
    <ChatSession />
    <RouterProvider router={router} />
  </AuthProvider></ProductMotion>;
}
