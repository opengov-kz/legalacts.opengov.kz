import Link from "next/link";
import { notFound } from "next/navigation";
import { getAnalyticsSummary, getAnalyticsTimeseries } from "@/lib/api-client";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { CategoryBarChart } from "@/components/analytics/CategoryBarChart";
import { TimeseriesLineChart } from "@/components/analytics/TimeseriesLineChart";

export default async function AnalyticsPage({
  params,
  searchParams,
}: {
  params: { locale: string };
  searchParams: { interval?: string };
}) {
  if (!isLocale(params.locale)) notFound();
  const locale = params.locale as Locale;
  const dict = getDictionary(locale);
  const interval = searchParams.interval === "week" ? "week" : "day";

  const [summary, timeseries] = await Promise.all([
    getAnalyticsSummary(),
    getAnalyticsTimeseries(interval),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-semibold">{dict.analytics.title}</h1>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{dict.analytics.bySection}</h2>
        <CategoryBarChart
          data={summary.documents_by_section.map((s) => ({ label: s.section, count: s.count }))}
          otherLabel={dict.analytics.other}
          tableCaption={dict.analytics.bySection}
          countLabel={dict.analytics.count}
        />
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{dict.analytics.byStatus}</h2>
        <CategoryBarChart
          data={summary.documents_by_status.map((s) => ({ label: s.status ?? "—", count: s.count }))}
          otherLabel={dict.analytics.other}
          tableCaption={dict.analytics.byStatus}
          countLabel={dict.analytics.count}
        />
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{dict.analytics.timeseries}</h2>
          <nav aria-label={dict.analytics.timeseries} className="flex gap-3 text-sm">
            <Link
              href={`/${locale}/analytics?interval=day`}
              aria-current={interval === "day" ? "page" : undefined}
              className={interval === "day" ? "font-semibold text-ink-primary" : "text-ink-secondary"}
            >
              {dict.analytics.day}
            </Link>
            <Link
              href={`/${locale}/analytics?interval=week`}
              aria-current={interval === "week" ? "page" : undefined}
              className={interval === "week" ? "font-semibold text-ink-primary" : "text-ink-secondary"}
            >
              {dict.analytics.week}
            </Link>
          </nav>
        </div>
        <TimeseriesLineChart
          points={timeseries}
          tableCaption={dict.analytics.timeseries}
          bucketLabel={dict.analytics.date}
          countLabel={dict.analytics.count}
        />
      </section>
    </div>
  );
}
