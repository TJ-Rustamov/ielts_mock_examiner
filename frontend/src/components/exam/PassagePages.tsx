/**
 * A reading passage shown as the book printed it: page crops stacked in order.
 */
import type { ExamSection } from '@/lib/exams';

export default function PassagePages({ section }: { section: ExamSection }) {
  return (
    <div className="space-y-3">
      {section.passage_pages.map((page, index) => (
        <img
          key={page.url}
          src={page.url}
          width={page.width || undefined}
          height={page.height || undefined}
          alt={`${section.label}, page ${index + 1}`}
          draggable={false}
          loading={index === 0 ? 'eager' : 'lazy'}
          className="h-auto w-full select-none rounded-md border bg-white"
        />
      ))}
    </div>
  );
}
