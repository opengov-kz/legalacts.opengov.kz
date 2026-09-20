import { NextResponse } from "next/server";
import { getCrawlStatus } from "@/lib/api-client";

export async function GET() {
  try {
    const status = await getCrawlStatus();
    return NextResponse.json(status);
  } catch (error) {
    console.error("GET /api/crawl/status failed:", error);
    return NextResponse.json({ error: "Внутренняя ошибка сервера" }, { status: 500 });
  }
}
