import { getDictionary } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE } from "@/lib/i18n/locales";

export default function NotFound() {
  const dict = getDictionary(DEFAULT_LOCALE);
  return (
    <div className="py-12 text-center">
      <h1 className="text-xl font-semibold">{dict.errors.notFoundTitle}</h1>
      <p className="mt-2 text-ink-secondary">{dict.errors.notFoundBody}</p>
    </div>
  );
}
