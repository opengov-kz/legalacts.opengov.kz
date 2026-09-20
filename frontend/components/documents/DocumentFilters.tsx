import Link from "next/link";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/locales";

const SECTIONS = ["npa", "kdrp", "arv", "withdraw"] as const;

function sectionHref(locale: Locale, section: string | undefined): string {
  return section ? `/${locale}/documents?section=${section}` : `/${locale}/documents`;
}

export function DocumentFilters({
  locale,
  section,
  dict,
}: {
  locale: Locale;
  section: string | undefined;
  dict: Dictionary;
}) {
  return (
    <nav aria-label={dict.documents.filterSection} className="flex flex-wrap gap-3 pb-4 text-sm">
      <Link href={sectionHref(locale, undefined)} aria-current={!section ? "page" : undefined}>
        {dict.documents.allSections}
      </Link>
      {SECTIONS.map((s) => (
        <Link key={s} href={sectionHref(locale, s)} aria-current={section === s ? "page" : undefined}>
          {s}
        </Link>
      ))}
    </nav>
  );
}
