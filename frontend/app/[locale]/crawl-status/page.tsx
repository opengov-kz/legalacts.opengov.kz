import { notFound } from "next/navigation";
import { getCrawlStatus } from "@/lib/api-client";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { CrawlStatusTable } from "@/components/crawl/CrawlStatusTable";
import { CrawlErrorsTable } from "@/components/crawl/CrawlErrorsTable";

export default async function CrawlStatusPage({ params }: { params: { locale: string } }) {
  if (!isLocale(params.locale)) notFound();
  const locale = params.locale as Locale;
  const dict = getDictionary(locale);

  const status = await getCrawlStatus();

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-semibold">{dict.crawlStatus.title}</h1>
      <CrawlStatusTable counts={status.counts} lastProcessedAt={status.last_processed_at} dict={dict} />
      <section>
        <h2 className="mb-2 text-lg font-semibold">{dict.crawlStatus.recentErrors}</h2>
        <CrawlErrorsTable errors={status.recent_errors} dict={dict} />
      </section>
    </div>
  );
}
