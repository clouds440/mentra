import { Outlet } from 'react-router';
import { MentraLogo } from '../components/brand/MentraLogo';
import { ArrowUpRight, BookOpen, Check, Compass } from 'lucide-react';

export function AuthLayout() {
  return (
    <main className="auth-layout">
      <section className="auth-story" aria-label="About Mentra">
        <div className="auth-brand"><MentraLogo /><span>mentra</span></div>
        <div className="auth-story-body">
          <p className="welcome-eyebrow"><span aria-hidden="true" />Your space to understand</p>
          <h2>Big ideas.<br />Small steps.<br /><em>Real understanding.</em></h2>
          <p>A thoughtful learning companion that connects your questions, your material, and your next breakthrough.</p>
          <div className="auth-learning-path" aria-hidden="true">
            <span><BookOpen size={18} />Bring your curiosity<Check size={15} /></span>
            <span><Compass size={18} />Find your own pace<Check size={15} /></span>
            <span><ArrowUpRight size={18} />Keep moving forward<span className="auth-path-dot" /></span>
          </div>
        </div>
        <p className="auth-story-footer">Made for the way you learn.</p>
      </section>
      <section className="auth-form-area" aria-label="Your account">
        <div className="auth-mobile-brand"><MentraLogo /><span>mentra</span></div>
        <div className="auth-form-content"><Outlet /></div>
        <p className="auth-form-footer">A quieter way to learn.</p>
      </section>
    </main>
  );
}
