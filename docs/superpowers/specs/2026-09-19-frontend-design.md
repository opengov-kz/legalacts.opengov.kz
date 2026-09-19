# Frontend: Public Read-Only Site for legalacts.opengov.kz Data

**Goal:** Build a public-facing website that lets external users browse scraped legal-act documents, read discussion comments, view crawl analytics, and check crawl status — backed by the existing FastAPI read API (`backend/app`). No new backend functionality is required; the API's shape (endpoints, filters, pagination) is treated as fixed for this phase.

**Backend context (already implemented, unchanged by this spec):**
- `GET /documents?section=&status=&page=` — paginated list (20/page), `raw_html_ru`/`raw_html_kk` deferred (not returned).
- `GET /documents/{id}` — single document with metadata + `comments[]`. No document body text is exposed via the API.
- `GET /analytics/summary` — counts by section, counts by status, totals.
- `GET /analytics/timeseries?interval=day|week` — document counts bucketed by `first_seen_at`.
- `GET /crawl/status` — queue counts by page_type/status, `last_processed_at`, last 20 errors.
- `GET /health` — no auth.
- All endpoints except `/health` require header `X-API-Key`.

## Architecture

Next.js 14+ (App Router) with TypeScript, deployed as a fourth Docker Compose service (`frontend`) alongside `db`/`api`/`worker`.

**Two layers inside the Next.js app:**

1. **BFF route handlers** (`app/api/*`) — thin server-side proxies to FastAPI. Each handler reads `FASTAPI_BASE_URL` and `API_KEY` from server-only environment variables, forwards incoming query parameters unchanged, attaches `X-API-Key`, and returns the FastAPI JSON response 1:1 (status code included). No transformation, aggregation, or caching logic beyond this — purely an isolation boundary so the API key never reaches the browser and so the frontend has a stable internal contract to build against, decoupled from the backend base URL.

2. **Server Components** (pages under `app/[locale]/*`) — fetch from the app's own internal `/api/*` routes using relative URLs (server-side `fetch`, no network hop outside the container). All data fetching for page render happens server-side; there is no client-side data fetching in v1 (no full-text search, no live polling), so no client state library is needed.

This keeps the API key isolated to two places (BFF route handlers only) while leaving room to later add client-side interactivity against the same `/api/*` routes without restructuring.

**Environment variables (server-only, never exposed to the client bundle):**
- `FASTAPI_BASE_URL` — e.g. `http://api:8000` inside Docker Compose.
- `API_KEY` — same value as the backend's `API_KEY` setting.

## Pages and routing

All content pages are locale-prefixed: `/[locale]/...` with `locale ∈ {ru, kk}`, default `ru`. Visiting `/` redirects to `/ru/documents`. An invalid locale segment renders `not-found`.

| Route | Purpose |
|---|---|
| `/[locale]/documents` | Catalog: table/cards of documents, filters for `section` and `status` (both as `<select>`-driven query params), pagination via `?page=`. Filter/page state lives entirely in the URL — changing a filter is a navigation, not a client fetch. |
| `/[locale]/documents/[id]` | Document detail: all metadata fields, comment thread (flat list ordered as returned, showing author/body/status/date), and an outbound link to the original page on `legalacts.egov.kz` (built from the stored `url` field) for the full document text. 404 (`not-found.tsx`) if the API returns 404. |
| `/[locale]/analytics` | `documents_by_section` and `documents_by_status` as bar charts; `timeseries` (day/week toggle) as a line chart. Chart implementation must follow the project's dataviz guidance at build time (color system, accessible legends/tooltips) — not decided further in this spec. |
| `/[locale]/crawl-status` | Queue counts by page_type/status, `last_processed_at`, table of the last 20 errors (url, page_type, error, processed_at). |

A shared header/nav provides links between the four pages and a locale switcher (`ru`/`kk`) that rewrites the current path's locale segment, preserving the rest of the path and query string.

## Internationalization (ru/kk)

- URL-based locale (`/ru/...`, `/kk/...`), no cookie-based switching in v1.
- Two concerns are localized independently:
  - **UI chrome** (nav labels, filter labels, table headers, buttons, error/empty states): a small static dictionary per locale (e.g. `lib/i18n/ru.ts`, `lib/i18n/kk.ts`), loaded by locale segment. No i18n framework — the string set is small and fixed.
  - **Document content**: `title_ru`/`title_kk` selected directly from the API response based on the active locale; other document fields (`status`, `doc_type`, `government_body`, dates) are stored in Russian only in the database (scraper limitation, unchanged) and are shown as-is regardless of locale. Comments (`author_name`, `body`) are stored in their original language and shown as-is.
- If `title_kk` is null for a document (scraper never had a kk pass succeed), fall back to `title_ru` with no special UI treatment beyond that fallback.

## Component/library choices

- **Styling:** Tailwind CSS + shadcn/ui (table, pagination, select, badge, card, button primitives) — no bespoke design system, neutral informational look.
- **Charts:** recharts, used only on `/analytics`.
- **Package manager:** npm (matches the project's otherwise plain tooling choices — pip for backend, no monorepo tooling).
- **No client-side state/data library** (no React Query/SWR) — v1 has no client-side fetches to manage.

## Error handling

Standard Next.js App Router mechanisms, no custom error pages:
- `not-found.tsx` per locale segment — used for unknown routes and for a document id that FastAPI returns 404 for.
- `error.tsx` per locale segment — catches thrown errors from Server Components (e.g., BFF route returning 5xx, FastAPI unreachable), shows a generic "something went wrong" message with a retry action (Next.js's built-in `reset()`).
- BFF route handlers pass through FastAPI's status code and body as-is; a non-2xx response causes the calling Server Component's `fetch` to be checked explicitly and `notFound()`/`throw` accordingly (404 → `notFound()`, anything else → thrown error caught by `error.tsx`).

## Testing

- **Vitest + React Testing Library:**
  - BFF route handlers: verify `X-API-Key` is attached, query params are forwarded unchanged, FastAPI status/body pass through unmodified, and the key is never present in any response body.
  - Key components (document card/table, filter bar, pagination, locale switcher, comment list) rendered with mock data.
- No Postgres/testcontainers dependency for frontend tests — all backend interaction is mocked at the `fetch` boundary.
- Backend's existing pytest suite (58/58) is unaffected and unchanged by this work.

## Docker / deployment

Fourth service in root `docker-compose.yml`, following the existing `api`/`worker` pattern:

```yaml
frontend:
  build: ./frontend
  ports:
    - "3000:3000"
  environment:
    FASTAPI_BASE_URL: http://api:8000
    API_KEY: ${API_KEY}
  depends_on:
    - api
  restart: unless-stopped
```

(`api` has no healthcheck today, so `depends_on` is a plain start-order dependency — same as how `api`/`worker` depend on `db`'s healthcheck, but without a check of its own since none exists to depend on.)

`frontend/Dockerfile` — multi-stage Next.js production build (`node:20-slim` or similar), consistent in spirit with `backend/Dockerfile`'s single-purpose container approach. `.env.example` at the repo root gains no new variables (reuses the existing `API_KEY`); `FASTAPI_BASE_URL` is fixed to the in-network service name and does not need to be user-configurable.

## Out of scope for v1

- Full-text search over documents (API has no search endpoint; adding one is a separate backend change).
- Rendering the original document body/HTML (raw_html_ru/kk is deferred by the API and not exposed; users follow the outbound link to the original site).
- Client-side live updates (e.g., auto-refreshing crawl status) — page reload is sufficient for a read-only public site.
- Authentication/accounts for site visitors — the site is fully public; `X-API-Key` is an internal server-to-server concern handled entirely by the BFF layer.
- Standalone deployment (e.g., Vercel) separate from the Docker Compose stack.
