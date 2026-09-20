import { NextResponse } from "next/server";
import { getAnalyticsSummary } from "@/lib/api-client";

export async function GET() {
  try {
    const summary = await getAnalyticsSummary();
    return NextResponse.json(summary);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }
}
