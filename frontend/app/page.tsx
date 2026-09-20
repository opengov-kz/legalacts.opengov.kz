import { redirect } from "next/navigation";
import { DEFAULT_LOCALE } from "@/lib/i18n/locales";

export default function Page() {
  redirect(`/${DEFAULT_LOCALE}/documents`);
}
