import { getDocuments } from "@/lib/api-client";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { notFound } from "next/navigation";
import { DocumentFilters } from "@/components/documents/DocumentFilters";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { Pagination } from "@/components/documents/Pagination";

const PAGE_SIZE = 20;

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

  const page = Number(searchParams.page ?? "1");
  const documents = await getDocuments({
    section: searchParams.section,
    status: searchParams.status,
    page,
  });

  return (
    <div>
      <h1 className="pb-4 text-2xl font-semibold">{dict.documents.title}</h1>
      <DocumentFilters locale={locale} section={searchParams.section} status={searchParams.status} dict={dict} />
      <DocumentTable documents={documents} locale={locale} dict={dict} />
      <Pagination
        locale={locale}
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
