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

The authenticated practice overview lists conversation records with pagination and a details drawer. The simulation APIs and SSE stream remain available for a future live simulation view.

```sh
pnpm build
pnpm lint
```

## UI components

Import controls from `src/components`. Their styles use the existing theme, including `.dark`, and are loaded once in `main.tsx`.

| Component | `variant` values (first is default) |
| --- | --- |
| `Button` | `primary`, `secondary`, `outline`, `ghost`, `danger` |
| `Card` | `outlined`, `elevated`, `muted` |
| `List` / `ListItem` | List: `divided`, `plain`, `bordered` |
| `Form` | `stacked`, `inline` |
| `TextInput`, `NumberInput`, `Dropdown`, `Textarea` | `outline`, `filled` |
| `Checkbox` | `default`, `panel` |
| `Modal`, `Drawer` | `default`, `muted` |

Buttons also accept `size="sm|md|lg"` (default `md`) and `fullWidth`. They default to `type="button"`; use `type="submit"` in forms. Controls accept native HTML props, refs, and event handlers. Fields accept `label`, `hint`, and `error` with generated accessible IDs. `NumberInput` supports native `min`, `max`, and `step`; use `event.currentTarget.valueAsNumber` when you need a number (an empty field yields `NaN`). Dropdown children are native `<option>` elements.

```tsx
<Form onSubmit={handleSubmit}>
  <TextInput label="Name" required variant="filled" />
  <NumberInput label="Quantity" min={1} step={1} />
  <Dropdown label="Priority" defaultValue="normal">
    <option value="normal">Normal</option>
    <option value="urgent">Urgent</option>
  </Dropdown>
  <Textarea label="Notes" hint="Optional" />
  <Checkbox label="Notify me" variant="panel" />
  <Button type="submit">Save</Button>
</Form>
```

## Registered modals and drawers

`components/Modal.tsx` and `components/Drawer.tsx` are presentation shells. Registry definitions, content layouts, context, and hooks live in `hooks/`. `OverlayProvider` wraps the tenant pages; wrap any other part of the app that needs these hooks too.

Add a content component in `hooks/layouts/` accepting `OverlayLayoutProps<YourData>`, then add an entry in `hooks/registry.ts` with `defineOverlay<YourData>({ title, component })`. Entries can set `description`, `size: 'sm' | 'md' | 'lg'`, `variant`, and drawer `side: 'left' | 'right'` (default right). The layout receives `data` and a `close()` function. Entries are passed directly, so TypeScript checks their expected data without string lookups or casts.

```tsx
import { useModal } from './hooks/useModal'
import { useDrawer } from './hooks/useDrawer'
import { overlayRegistry } from './hooks/registry'

// Inside a component under OverlayProvider:
const { openModal, closeModal } = useModal()
const { openDrawer, closeDrawer } = useDrawer()

<Button onClick={() => openModal(overlayRegistry.providerDetails, session)}>
  View profile
</Button>
<Button onClick={() => openDrawer(overlayRegistry.providerDetails, session)}>
  Open details drawer
</Button>
```

One overlay is active at a time; opening another replaces it and resets the content state. Close with the layout’s `close()`, the matching hook’s close function, the close button, Escape, or a backdrop click. Native modal dialogs trap focus and make the page behind them inert; closing restores focus to the trigger and restores page scrolling. The provider unmounts when leaving the tenant pages so overlays cannot carry over to another practice. Shells can also be used directly with `open`, `onClose`, `title`, children, and an optional `footer`.

Interaction styles include button hover lift and press feedback, input focus rings, checkbox states, and link feedback. Modals fade and scale; drawers slide from their configured side. Closing keeps focus and scroll locked until the exit animation finishes. For directly controlled shells, keep them mounted while `open={false}` and use `onExited` if you need to unmount afterward; the registry provider handles this automatically. Reduced-motion preferences disable movement and transitions while retaining focus and state highlights.

## Conversation table

The authenticated overview reads `GET /api/practices/{practice}/conversations?limit=20&offset=0`, ordered newest first and scoped to the cookie's practice. Refresh reloads the current page; row selection opens the record metadata drawer. The top-right profile badge opens provider details, alongside practice switching and sign out.

`Table<Row>` accepts `data`, `columns`, and a stable `rowKey`. Each `TableColumn<Row>` specifies `id`, `name`, and `data` (a property key or row-render function), plus optional `className`, `headerClassName`, `style`, and `align`. Use `variant="default|striped|compact"`, `loading`, `emptyMessage`, and `caption` as needed. Header/footer objects accept `title`, `subtitle`, `content`, and `actions`.

```tsx
const columns: TableColumn<ConversationRecord>[] = [
  { id: 'name', name: 'Conversation', data: 'name' },
  { id: 'status', name: 'Status', data: row => <strong>{row.status}</strong> },
]
<Table
  data={records}
  columns={columns}
  rowKey={row => row.id}
  onRowClick={row => openDrawer(overlayRegistry.conversationDetails, row)}
  header={{ title: 'Conversations', subtitle: 'Your practice’s calls' }}
  footer={{ subtitle: `${records.length} records`, actions: <Button>Refresh</Button> }}
/>
```

`onRowClick` is optional. When supplied, the first cell becomes a keyboard-accessible button; use plain text in that first column and put additional links/buttons in other columns. Those controls keep their own click behavior. `rowLabel` can supply a descriptive accessible button name. Wide tables scroll horizontally without overflowing the page.

## Sidebar and practice pages

Authenticated routes are `/{practice}/conversations`, `/{practice}/patients`, and `/{practice}/providers`. The practice root redirects to conversations. Page components live in `src/pages/`; all three use `Table`. Patient columns show name, date of birth, and the current practice's medical record number; provider columns show name, NPI, and provider ID. Both directories support refresh, pagination, and loading/error/empty states.

`Sidebar` in `components/` is controlled with `open`, `onOpenChange`, and `links: { label, to, icon }[]`. It expands in normal document flow, resizing the main content, and collapses to an accessible icon rail. The toggle exposes its expanded state and active links use `aria-current`. It starts collapsed on smaller screens; reduced-motion settings disable the width transition.

The directory endpoints `GET /api/practices/{practice}/patients` and `/providers` accept `limit` (1–100) and `offset`. They require the practice cookie and query patient/provider practice memberships, returning `{ items, total }` with deterministic name ordering. Patient dates are displayed as date-only values to avoid timezone shifts.

## Simulation controls

The navbar **Seed data** button seeds supporting records and simulation samples, then refreshes the current table. It does not create recorded conversations; those appear only after **Run simulation**. Above the conversations table, choose an unused starting scenario or **Select random sample**, then **Run simulation**. The existing practice-scoped simulation endpoints replay its linked calls; the table refreshes during replay.

**Clear simulated data** deletes all runtime conversation, action-execution, and workflow-run rows in `kyron` across all practices, clears authorization references to deleted actions, and resets every simulation source to unused. Patient, provider, clinical, and insurance records remain. Clear and seed reserve the simulator until complete; either returns a busy error during active replay. These are authenticated, origin-checked controls for the local demo, and their data operations affect all practices.

Conversation rows open a `size="screen"` modal with Details, Transcript, Actions, and Evaluation tabs. Details and Transcript are connected; the other tabs are explicit placeholders. The transcript first loads an atomic snapshot from `GET /api/practices/{practice}/conversations/{id}`, then subscribes to `/events?conversation_id={id}&after={cursor}`. Event IDs resume the stream and per-call sequences prevent duplicate words. Completed records use the saved transcript. Closing the modal closes its stream; switching tabs preserves it. Scrolling up pauses automatic scrolling, and **Jump to latest** resumes it.

## Rules browser and shared tabs

`/{practice}/rules` loads the available workflow versions as tabs and draws their stored rule graph with labeled arrows and terminal outcomes. The graph scrolls in both directions and has zoom controls. Selecting a rule opens a registry drawer containing the full checklist, action instructions, actor/timing, expected return fields, and all branch conditions. Only persisted workflows appear; the current seed includes one workflow version.

`Tabs` in `components/Tabs.tsx` accepts `items: { value, label, content, disabled? }[]`, controlled `value` / `onValueChange`, and an accessible `label`. It supports `underline` and `pills` variants, Arrow/Home/End keyboard navigation, and associated tab panels. Panels stay mounted by default; pass `keepMounted={false}` for lazy content. Both the Rules page and conversation modal import this component; changing conversation tabs preserves its live transcript connection.

The conversation Actions tab polls the practice-scoped actions endpoint during a call. It renders the same decision-tree component with completed rules, the current rule, and only the branch conditions actually taken highlighted. Selecting a node shows that rule's checklist, evidence, return values and missing fields. Evaluation displays the saved summary, sentiment, continuation decision and metrics. Workflow observations carried from a parent call preserve the path across follow-ups.

Live conversation modals include **Cancel simulation**. Cancellation preserves the partial transcript, marks the call failed, refreshes table/actions state, and removes the speaking indicator. Completed calls do not show the button.
