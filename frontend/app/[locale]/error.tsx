"use client";

import { getDictionary } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE } from "@/lib/i18n/locales";
import { Button } from "@/components/ui/button";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  const dict = getDictionary(DEFAULT_LOCALE);
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
