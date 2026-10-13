import { lazy } from 'react';
import { RouteBoundary } from './components/ui/RouteBoundary';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { AuthLayout } from './layouts/AuthLayout';
import { AuthProvider } from './components/auth/AuthProvider';
import { RequireAuth, RequireGuest } from './components/auth/AuthRoutes';
import { ChatSession } from './components/chat/ChatSession';
import { ProfileReady, RequireOnboardingComplete } from './components/student-profile/ProfileRoutes';

const LoginPage = lazy(() => import('./pages/LoginPage').then(module => ({ default: module.LoginPage })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(module => ({ default: module.RegisterPage })));
const AssessmentsPage = lazy(() => import('./pages/AssessmentsPage').then(module => ({ default: module.AssessmentsPage })));
const ChatPage = lazy(() => import('./pages/ChatPage').then(module => ({ default: module.ChatPage })));

const LibraryPage = lazy(() => import('./pages/LibraryPage').then(module => ({ default: module.LibraryPage })));
const AddMaterialPage = lazy(() => import('./pages/AddMaterialPage').then(module => ({ default: module.AddMaterialPage })));
const MaterialDetailPage = lazy(() => import('./pages/MaterialDetailPage').then(module => ({ default: module.MaterialDetailPage })));
const ProgressPage = lazy(() => import('./pages/ProgressPage').then(module => ({ default: module.ProgressPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(module => ({ default: module.SettingsPage })));
const NotificationsPage = lazy(() => import('./pages/NotificationsPage').then(module => ({ default: module.NotificationsPage })));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then(module => ({ default: module.OnboardingPage })));


function EventsRedirect() {
  const location = useLocation(); const params = new URLSearchParams(location.search); params.set('tab', 'events');
  return <Navigate replace to={{ pathname: '/progress', search: params.toString() }} />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ChatSession />
        <Routes>
          <Route element={<RequireGuest />}>
            <Route element={<AuthLayout />}>
              <Route path="login" element={<RouteBoundary><LoginPage /></RouteBoundary>} />
              <Route path="register" element={<RouteBoundary><RegisterPage /></RouteBoundary>} />
            </Route>
          </Route>
          <Route element={<RequireAuth />}>
            <Route element={<ProfileReady />}>
              <Route path="onboarding" element={<RouteBoundary><OnboardingPage /></RouteBoundary>} />
              <Route path="calibration" element={<RouteBoundary><OnboardingPage calibrationOnly /></RouteBoundary>} />
              <Route element={<RequireOnboardingComplete />}>
                <Route element={<AppLayout />}>
                  <Route index element={<RouteBoundary><ChatPage /></RouteBoundary>} />
                  <Route path="chat/:conversationId" element={<RouteBoundary><ChatPage /></RouteBoundary>} />
                  <Route path="library" element={<RouteBoundary><LibraryPage /></RouteBoundary>} />
                  <Route path="library/new" element={<RouteBoundary><AddMaterialPage /></RouteBoundary>} />
                  <Route path="library/:documentId" element={<RouteBoundary><MaterialDetailPage /></RouteBoundary>} />
                  <Route path="progress" element={<RouteBoundary><ProgressPage /></RouteBoundary>} />
                  <Route path="assessments" element={<RouteBoundary><AssessmentsPage /></RouteBoundary>} />
                  <Route path="settings" element={<RouteBoundary><SettingsPage /></RouteBoundary>} />
                  <Route path="notifications" element={<RouteBoundary><NotificationsPage /></RouteBoundary>} />
                  <Route path="events" element={<EventsRedirect />} />
                  <Route path="*" element={<Navigate replace to="/" />} />
                </Route>
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
