import { NextRequest, NextResponse } from "next/server";
import { getAnalyticsTimeseries } from "@/lib/api-client";

export async function GET(request: NextRequest) {
  const interval = request.nextUrl.searchParams.get("interval") === "week" ? "week" : "day";
  try {
    const points = await getAnalyticsTimeseries(interval);
    return NextResponse.json(points);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }
}
