import { Navigate, useSearchParams } from 'react-router-dom';
import { LearningProgress } from '../components/learning/LearningProgress';

export function ProgressPage() {
  const [params] = useSearchParams();
  if (params.get('tab') === 'mistakes') return <Navigate replace to={`/assessments?${params}`} />;
  return <LearningProgress />;
}
