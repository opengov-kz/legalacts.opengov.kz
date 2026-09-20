"use client";

import { getDictionary } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE } from "@/lib/i18n/locales";
import { Button } from "@/components/ui/button";
import "./globals.css";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const dict = getDictionary(DEFAULT_LOCALE);
  return (
    <html lang={DEFAULT_LOCALE}>
      <body>
        <div className="py-12 text-center">
          <h1 className="text-xl font-semibold">{dict.errors.genericTitle}</h1>
          <p className="mt-2 text-ink-secondary">{dict.errors.genericBody}</p>
          <Button className="mt-4" onClick={reset}>
            {dict.errors.retry}
          </Button>
        </div>
      </body>
    </html>
  );
}
