import { getDocuments } from "@/lib/api-client";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { notFound } from "next/navigation";
import { DocumentFilters } from "@/components/documents/DocumentFilters";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { Pagination } from "@/components/documents/Pagination";

// Must match backend/app/routers/documents.py's page size — the API returns a plain
// array with no total count, so a full page is the only signal that more pages exist.
const PAGE_SIZE = 20;

function parsePage(raw: string | undefined): number {
  const n = Math.trunc(Number(raw ?? "1"));
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

export default async function DocumentsPage({
  params,
  searchParams,
}: {
  params: { locale: string };
  searchParams: { section?: string; status?: string; page?: string };
}) {
  if (!isLocale(params.locale)) notFound();
  const locale = params.locale as Locale;
  const dict = getDictionary(locale);

  const page = parsePage(searchParams.page);
  const documents = await getDocuments({
    section: searchParams.section,
    status: searchParams.status,
    page,
  });

  return (
    <div>
      <h1 className="pb-4 text-2xl font-semibold">{dict.documents.title}</h1>
      <DocumentFilters locale={locale} section={searchParams.section} dict={dict} />
      <DocumentTable documents={documents} locale={locale} dict={dict} />
      <Pagination
        page={page}
        hasNextPage={documents.length === PAGE_SIZE}
        basePath={`/${locale}/documents`}
        searchParams={{
          ...(searchParams.section ? { section: searchParams.section } : {}),
          ...(searchParams.status ? { status: searchParams.status } : {}),
        }}
        dict={dict}
      />
    </div>
  );
}
