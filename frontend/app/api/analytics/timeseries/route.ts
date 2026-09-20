import { NextRequest, NextResponse } from "next/server";
import { getAnalyticsTimeseries } from "@/lib/api-client";

export async function GET(request: NextRequest) {
  const interval = request.nextUrl.searchParams.get("interval") === "week" ? "week" : "day";
  try {
    const points = await getAnalyticsTimeseries(interval);
    return NextResponse.json(points);
  } catch (error) {
    console.error("GET /api/analytics/timeseries failed:", error);
    return NextResponse.json({ error: "Внутренняя ошибка сервера" }, { status: 500 });
  }
}
