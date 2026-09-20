"use client";

import { useParams } from "next/navigation";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE, isLocale } from "@/lib/i18n/locales";
import { Button } from "@/components/ui/button";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  const params = useParams();
  const localeParam = params?.locale;
  const locale = typeof localeParam === "string" && isLocale(localeParam) ? localeParam : DEFAULT_LOCALE;
  const dict = getDictionary(locale);
  return (
    <div className="py-12 text-center">
      <h1 className="text-xl font-semibold">{dict.errors.genericTitle}</h1>
      <p className="mt-2 text-ink-secondary">{dict.errors.genericBody}</p>
      <Button className="mt-4" onClick={reset}>
        {dict.errors.retry}
      </Button>
    </div>
  );
}
