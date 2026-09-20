import { NextResponse } from "next/server";
import { getCrawlStatus } from "@/lib/api-client";

export async function GET() {
  try {
    const status = await getCrawlStatus();
    return NextResponse.json(status);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }
}
