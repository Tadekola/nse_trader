/**
 * Next.js Route Handler for scan trigger.
 * Bypasses the rewrite proxy to allow a longer timeout (180s)
 * for this long-running backend operation.
 */
import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST() {
  try {
    const res = await fetch(`${BACKEND}/api/v1/scan/trigger`, {
      method: "POST",
      signal: AbortSignal.timeout(180_000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { success: false, message: `Proxy error: ${msg}` },
      { status: 502 },
    );
  }
}
