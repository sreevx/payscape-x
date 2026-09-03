/**
 * Application-level Demo Mode.
 *
 * Demo Mode controls whether synthetic data is surfaced in the UI. Since
 * Part 2 the environment runs on the backend's deterministic synthetic
 * dataset (NovaCart Commerce) — never real merchant or payment data — so
 * the indicator reads "DEMO · SYNTHETIC DATA".
 *
 * Set `NEXT_PUBLIC_DEMO_MODE=false` to disable the demo layer.
 */

const isDemoMode = (): boolean =>
  (process.env.NEXT_PUBLIC_DEMO_MODE ?? "true").toLowerCase() !== "false";

export const DEMO_MODE: boolean = isDemoMode();

export const DEMO_MODE_LABEL = "DEMO · SYNTHETIC DATA";

/** Environment label shown in the top bar (e.g. dev / staging / prod). */
export const APP_ENV: string = process.env.NEXT_PUBLIC_APP_ENV ?? "development";