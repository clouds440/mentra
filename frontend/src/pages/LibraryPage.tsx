import { BookOpen, FileImage, FileText, Presentation } from 'lucide-react';
import { Button } from '../components/ui';
import { WorkspacePlaceholder } from './WorkspacePlaceholder';

const materialTypes = [
  { label: 'PDFs', icon: FileText },
  { label: 'Documents', icon: FileText },
  { label: 'Slides', icon: Presentation },
  { label: 'Text', icon: FileText },
  { label: 'Images', icon: FileImage },
];

export function LibraryPage() {
  return (
    <WorkspacePlaceholder
      description="A calm home for the material you choose to learn from."
      emptyDescription="When material is available in Mentra, you’ll be able to find it here and study from it in chat."
      emptyTitle="Your study material will live here."
      eyebrow="Your learning space"
      icon={<BookOpen aria-hidden="true" size={19} strokeWidth={1.7} />}
      title="Library"
    >
      <div className="mt-8 flex flex-col gap-5 border-b border-white/[0.07] pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs text-slate-500">Content types planned for the library</p>
          <ul aria-label="Potential material types" className="mt-3 flex flex-wrap gap-2">
            {materialTypes.map(({ label, icon: Icon }) => (
              <li
                className="inline-flex items-center gap-2 rounded-lg border border-white/[0.07] px-3 py-2 text-xs text-slate-400"
                key={label}
              >
                <Icon aria-hidden="true" size={14} />
                {label}
              </li>
            ))}
          </ul>
        </div>
        <Button disabled size="sm" variant="secondary">
          Add material
        </Button>
      </div>
    </WorkspacePlaceholder>
  );
}
