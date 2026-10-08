import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { AuthLayout } from './layouts/AuthLayout';
import { AuthProvider } from './components/auth/AuthProvider';
import { RequireAuth, RequireGuest } from './components/auth/AuthRoutes';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { AssessmentsPage } from './pages/AssessmentsPage';
import { ChatPage } from './pages/ChatPage';
import { LibraryPage } from './pages/LibraryPage';
import { MaterialDetailPage } from './pages/MaterialDetailPage';
import { ProgressPage } from './pages/ProgressPage';
import { SettingsPage } from './pages/SettingsPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { ProfileReady, RequireOnboardingComplete } from './components/student-profile/ProfileRoutes';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<RequireGuest />}>
            <Route element={<AuthLayout />}>
              <Route path="login" element={<LoginPage />} />
              <Route path="register" element={<RegisterPage />} />
            </Route>
          </Route>
          <Route element={<RequireAuth />}>
            <Route element={<ProfileReady />}>
              <Route path="onboarding" element={<OnboardingPage />} />
              <Route path="calibration" element={<OnboardingPage calibrationOnly />} />
              <Route element={<RequireOnboardingComplete />}>
                <Route element={<AppLayout />}>
                  <Route index element={<ChatPage />} />
                  <Route path="library" element={<LibraryPage />} />
                  <Route path="library/:documentId" element={<MaterialDetailPage />} />
                  <Route path="progress" element={<ProgressPage />} />
                  <Route path="assessments" element={<AssessmentsPage />} />
                  <Route path="settings" element={<SettingsPage />} />
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
