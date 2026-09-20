"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { getDictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/locales";
import { LocaleSwitcher } from "./LocaleSwitcher";

export function SiteHeader({ locale }: { locale: Locale }) {
  const dict = getDictionary(locale);
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const qs = searchParams.toString();
  const currentPath = qs ? `${pathname}?${qs}` : pathname;

  return (
    <header className="border-b border-gridline">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <nav className="flex gap-4 text-sm font-medium">
          <Link href={`/${locale}/documents`}>{dict.nav.documents}</Link>
          <Link href={`/${locale}/analytics`}>{dict.nav.analytics}</Link>
          <Link href={`/${locale}/crawl-status`}>{dict.nav.crawlStatus}</Link>
        </nav>
        <LocaleSwitcher activeLocale={locale} currentPath={currentPath} dict={dict} />
      </div>
    </header>
  );
}
