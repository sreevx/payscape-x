"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth } from "@/lib/api-client";

export type BackendConnectionState = "checking" | "connected" | "unavailable";

/**
 * Polls `GET /api/v1/health` on an interval and reports the real backend
 * state. Never fakes the connection — if the backend is down the hook
 * reports "unavailable" and the UI shows a clear fallback state.
 */
export function useBackendHealth(
  intervalMs: number = 30_000
): { state: BackendConnectionState; refetch: () => Promise<void> } {
  const [state, setState] = useState<BackendConnectionState>("checking");
  const inFlight = useRef(false);

  const check = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const health = await getHealth();
      setState(health.status === "ok" ? "connected" : "unavailable");
    } catch {
      setState("unavailable");
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    // Defer the first probe out of the effect body (state updates happen on
    // the fetch resolution) and poll afterwards on the interval.
    const first = window.setTimeout(() => void check(), 0);
    const id = window.setInterval(() => void check(), intervalMs);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [check, intervalMs]);

  return { state, refetch: check };
}