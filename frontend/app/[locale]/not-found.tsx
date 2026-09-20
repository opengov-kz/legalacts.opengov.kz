"use client";

import { usePathname } from "next/navigation";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE, isLocale } from "@/lib/i18n/locales";

export default function NotFound() {
  const pathname = usePathname();
  const segment = pathname?.split("/")[1];
  const locale = segment && isLocale(segment) ? segment : DEFAULT_LOCALE;
  const dict = getDictionary(locale);

  return (
    <div className="py-12 text-center">
      <h1 className="text-xl font-semibold">{dict.errors.notFoundTitle}</h1>
      <p className="mt-2 text-ink-secondary">{dict.errors.notFoundBody}</p>
    </div>
  );
}
