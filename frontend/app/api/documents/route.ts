import { NextRequest, NextResponse } from "next/server";
import { getDocuments } from "@/lib/api-client";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const page = params.get("page");

  try {
    const documents = await getDocuments({
      section: params.get("section") ?? undefined,
      status: params.get("status") ?? undefined,
      page: page ? Number(page) : undefined,
    });
    return NextResponse.json(documents);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }
}
