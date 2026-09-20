import { redirect } from "next/navigation";
import { DEFAULT_LOCALE } from "@/lib/i18n/locales";

export const dynamic = "force-dynamic";

export default function Page() {
  redirect(`/${DEFAULT_LOCALE}/documents`);
}
