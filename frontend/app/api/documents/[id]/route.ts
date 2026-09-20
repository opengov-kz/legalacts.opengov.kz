import { NextRequest, NextResponse } from "next/server";
import { getDocument } from "@/lib/api-client";

export async function GET(_request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const document = await getDocument(Number(params.id));
    if (document === null) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }
    return NextResponse.json(document);
  } catch (error) {
    console.error(`GET /api/documents/${params.id} failed:`, error);
    return NextResponse.json({ error: "Внутренняя ошибка сервера" }, { status: 500 });
  }
}
