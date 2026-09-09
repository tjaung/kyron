# Provider portal

React, TypeScript, Vite, and pnpm. The theme in `src/index.css` supplies light/dark colors and Inter typography.

```sh
pnpm install
pnpm dev
```

Open **http://localhost:5173**. The dev server proxies `/api` to FastAPI at `http://localhost:8000`; set `API_PROXY_TARGET` to change that target. Compose runs this client as well, so stop its client service (`docker compose stop client`) before running a second local dev server on the same port.

## Login flow

1. `/` (or `/auth`) shows a practice dropdown.
2. Selecting a practice navigates to `/{practice}/auth`.
3. Sign in with `lower(firstname.lastname)` and password `password`.
4. Successful login redirects to `/{practice}`, the protected practice landing page.
5. Sign out deletes the cookie and returns to that practice’s auth page.

The seeded provider is **taylor.demo**, affiliated with both practices. For example, `/harbor-family-practice/auth` and `/cedar-primary-care/auth` each require a session for that practice.

`src/auth/AuthProvider.tsx` restores the session with `GET /api/practices/{practice}/auth/me` on mount. The cookie is HttpOnly; React never reads or stores the JWT. A cookie for another practice does not sign you into the selected practice. The provider is keyed by practice so changing tenants clears the previous in-memory identity before checking the new session.

This first client screen implements authentication and a signed-in landing page. The existing simulation APIs and SSE stream are protected and practice-scoped; the simulator dashboard can consume them from the authenticated client next.

```sh
pnpm build
pnpm lint
```
