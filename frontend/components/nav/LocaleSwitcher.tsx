import Link from "next/link";
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
}: {
  activeLocale: Locale;
  currentPath: string;
}) {
  return (
    <nav aria-label="Language" className="flex gap-2 text-sm">
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
