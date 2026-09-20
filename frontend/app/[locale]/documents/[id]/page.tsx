import { notFound } from "next/navigation";
import { getDocument } from "@/lib/api-client";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { isLocale, type Locale } from "@/lib/i18n/locales";
import { DocumentMeta } from "@/components/documents/DocumentMeta";
import { CommentList } from "@/components/documents/CommentList";

export default async function DocumentDetailPage({
  params,
}: {
  params: { locale: string; id: string };
}) {
  if (!isLocale(params.locale)) notFound();
  const locale = params.locale as Locale;
  const dict = getDictionary(locale);

  const document = await getDocument(Number(params.id));
  if (document === null) notFound();

  return (
    <div>
      <DocumentMeta document={document} locale={locale} dict={dict} />
      <h2 className="mt-8 text-lg font-semibold">{dict.documents.comments}</h2>
      <div className="mt-3">
        <CommentList comments={document.comments} dict={dict} />
      </div>
    </div>
  );
}
