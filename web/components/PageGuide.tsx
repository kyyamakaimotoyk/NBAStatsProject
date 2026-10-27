"use client";

import { useLang } from "@/lib/i18n";
import { pageGuides, type GuideKey } from "@/lib/pageGuides";

// The written "how to read this page" section at the bottom of each data page.
// Plain prose, no data fetch — so it lands in the prerendered HTML and gives
// readers (and crawlers) real text even before the charts load.
export default function PageGuide({ page }: { page: GuideKey }) {
  const { lang } = useLang();
  const guide = pageGuides[page][lang];
  return (
    <section className="page-guide" aria-labelledby={`guide-${page}`}>
      <h2 id={`guide-${page}`}>{guide.title}</h2>
      {guide.sections.map((s) => (
        <div key={s.heading}>
          <h3>{s.heading}</h3>
          {s.body.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      ))}
    </section>
  );
}
