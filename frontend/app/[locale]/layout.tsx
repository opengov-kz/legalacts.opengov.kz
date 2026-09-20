import { Suspense } from "react";
import { notFound } from "next/navigation";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { SiteHeader } from "@/components/nav/SiteHeader";

export function generateStaticParams() {
  return [{ locale: "ru" }, { locale: "kk" }];
}

export default function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  if (!isLocale(params.locale)) {
    notFound();
  }
  const locale = params.locale as Locale;

  return (
    <div className="mx-auto max-w-5xl">
      <Suspense fallback={null}>
        <SiteHeader locale={locale} />
      </Suspense>
      <main className="px-4 py-6">{children}</main>
    </div>
  );
}
