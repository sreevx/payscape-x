# PAYSCAPE-X Frontend

Next.js 16 control-center UI for PAYSCAPE-X. See the repository root
`README.md` for setup, environment variables and architecture.

```bash
npm install
cp .env.example .env.local
npm run dev          # http://localhost:3000
npm run build        # production build
npm run typecheck    # tsc --noEmit
npm test             # vitest (tests/ folder)
```

Key folders:

- `app/` — routes (`/dashboard`, `/transactions/[id]`, `/investigation/[id]`,
  `/failures`, `/simulation`, `/actions`, `/events`, `/settings`)
- `components/` — layout shell, dashboard sections, shared primitives, ui/
- `lib/` — typed API client, demo-mode flag, demo-data seed layer
- `hooks/` — backend health polling
- `types/` — shared domain types mirroring the backend entities
