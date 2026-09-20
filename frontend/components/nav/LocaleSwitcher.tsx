import Link from "next/link";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import { LOCALES, type Locale } from "@/lib/i18n/locales";

function pathWithLocale(currentPath: string, activeLocale: Locale, targetLocale: Locale): string {
  const [pathOnly, query] = currentPath.split("?");
  const segments = pathOnly.split("/").filter(Boolean);
  segments[0] = targetLocale;
  const newPath = `/${segments.join("/")}`;
  return query ? `${newPath}?${query}` : newPath;
}

export function LocaleSwitcher({
  activeLocale,
  currentPath,
  dict,
}: {
  activeLocale: Locale;
  currentPath: string;
  dict: Dictionary;
}) {
  return (
    <nav aria-label={dict.nav.language} className="flex gap-2 text-sm">
      {LOCALES.map((locale) => (
        <Link
          key={locale}
          href={pathWithLocale(currentPath, activeLocale, locale)}
          aria-current={locale === activeLocale ? "page" : undefined}
          className={locale === activeLocale ? "font-semibold text-ink-primary" : "text-ink-secondary"}
        >
          {locale.toUpperCase()}
        </Link>
      ))}
    </nav>
  );
}
