import { LazyMotion, MotionConfig, m, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';
const loadFeatures = () => import('./motionFeatures').then(module => module.default);

/** Share the small DOM animation feature set; never animate the message tree. */
export function ProductMotion({ children }: { children: ReactNode }) {
  return <LazyMotion features={loadFeatures} strict><MotionConfig reducedMotion="user" transition={{ type: 'spring', stiffness: 380, damping: 34 }}>{children}</MotionConfig></LazyMotion>;
}

export { m, useReducedMotion };
