import { NextResponse } from "next/server";
import { getAnalyticsSummary } from "@/lib/api-client";

export async function GET() {
  try {
    const summary = await getAnalyticsSummary();
    return NextResponse.json(summary);
  } catch (error) {
    console.error("GET /api/analytics/summary failed:", error);
    return NextResponse.json({ error: "Внутренняя ошибка сервера" }, { status: 500 });
  }
}
