# DevOpsSentinel Web — GUI Capability Matrix

**Audit basis.** Every row below was produced by reading the actual source in this
repository (`frontend/src/**`, `backend/app/**`) and by live-probing the running
container. Nothing here is assumed or aspirational. Rows verified against a running
system are marked **[live]**; rows established by reading code are marked **[code]**.

**Audited revision.** `devopssentinel-web:1.2.3` (backend schema 1.0).
**Audit scope.** 66 frontend source files (≈7.4k lines), 25 backend modules,
94 HTTP routes, 57 exported query hooks.

## Legend

| STATUS | Meaning |
| --- | --- |
| `PRODUCTION READY` | Complete, tested, accessible, no known gap |
| `GOOD` | Works correctly; cosmetic or minor gaps only |
| `PARTIAL` | Renders, but a meaningful part of the engine's data is unreachable |
| `SHALLOW` | Shows a subset while the backend offers substantially more |
| `BROKEN` | Does not work as intended |
| `DUPLICATED` | Reimplements something that already has a shared component |
| `INCONSISTENT` | Diverges from the application's own conventions |
| `MISSING` | Required capability absent from the GUI |
| `NEEDS REDESIGN` | Present but structurally wrong for SRE work |

## 1. Cross-cutting infrastructure

| Area | Component | Evidence | STATUS |
| --- | --- | --- | --- |
| Routing | `App.tsx` — 23 routes, `BrowserRouter`, SPA fallback in `main.py` | **[code]** deep-link refresh works **[live]** | `GOOD` |
| **Route error isolation** | none — no `ErrorBoundary` anywhere | **[code]** one component throw blanks the whole app | `MISSING` (§131) |
| **Code splitting** | none — zero `React.lazy` / `Suspense` | **[code]** single 941 kB JS / 286 kB gzip bundle | `MISSING` (§148, §149) |
| **URL state** | `AppContext` persists context/namespace to `localStorage` only | **[code]** no `useSearchParams` anywhere; views are not shareable | `MISSING` (§120, §121, §206) |
| Scope switching | `TopBar` context + namespace selects | **[code]** | `GOOD` |
| **Context-switch safety** | no cache clear or request cancellation on scope change | **[code]** query keys include scope so responses cannot cross-contaminate, but §196–§200 are unaddressed | `PARTIAL` (§196–§200) |
| Design tokens | `index.css` — CSS custom properties per theme | **[code]** centralised, 8 themes | `PRODUCTION READY` (§236) |
| Themes | 8 (6 dark / 2 light) + system auto, `lib/themes.ts` | **[code]** both kinds fully specified | `PRODUCTION READY` (§20) |
| Status vocabulary | `lib/status.ts` — one `Severity` union, glyph + label + colour | **[code]** single source of truth | `PRODUCTION READY` (§18, §19) |
| Status rendering | `StatusPill` — icon + text + colour, never colour alone | **[code]** | `PRODUCTION READY` (§19, §21) |
| Data freshness | `Freshness` — `LIVE`/`CACHE`/`PARTIAL`/`UNAVAILABLE` + age + duration | **[code]** | `PRODUCTION READY` (§63) |
| Partial state | `PartialBanner` + `Envelope.partial` | **[code]** | `PRODUCTION READY` (§59, §140) |
| Empty / error state | `EmptyState`, `ErrorState` (impact + next safe action + raw details) | **[code]** | `PRODUCTION READY` (§138, §139, §335–§337) |
| Loading state | `LoadingRows` skeleton | **[code]** | `GOOD` (§60, §189) |
| Live refresh | `LiveRefresher` — `setInterval` + `refetchQueries` on non-identity keys | **[code]** explicit, visible, pauses on a hidden tab | `GOOD` (§54, §55) |
| **Live transport** | **SSE exists (`api/sse.py`, `/api/v1/live`, `/api/v1/logs`) but the frontend has zero `EventSource`** | **[code]** 0 matches; polling only | `MISSING` (§53) |
| Cache discipline | TanStack Query, 15 s `staleTime`, `retry: 1`, no refetch-on-focus | **[code]** | `GOOD` (§142) |
| **Retry policy** | blanket `retry: 1` — retries RBAC/404/400 too | **[code]** | `INCONSISTENT` (§144) |
| Command palette | `CommandPalette` — `Ctrl/Cmd+K`, `/`, arrow keys, `role=listbox` | **[code]** | `GOOD` (§11) |
| **Palette coverage** | routes + Pods + Certificates + GitOps **only**; no Services, PVCs, Findings, namespaces, recents | **[code]** | `PARTIAL` (§11, §13) |
| **Palette query cost** | fires 3 cluster-wide reads on every open | **[code]** | `INCONSISTENT` (§145, §146) |
| **Backend `/search`** | `GET /api/v1/search` exists and is never called | **[code]** | `MISSING` (§11, §12) |
| **Search prefixes** | `pod:` `cert:` `status:` `ns:` not supported | **[code]** | `MISSING` (§12) |
| Shortcut help | `?` opens the **palette**, not a reference sheet | **[code]** | `INCONSISTENT` (§127) |
| Keyboard chords | `g d/p/l/x/g/c/n/s/f/t/e` in `AppShell` | **[code]** partial set; no `g w`, `g o`, `r`, `Esc` | `PARTIAL` (§126) |
| Focus management | Radix `Dialog` used for the palette | **[code]** Radix focus/ARIA preserved | `PRODUCTION READY` (§128) |
| Breadcrumbs | `Breadcrumbs` + `breadcrumbFor` | **[code]** | `GOOD` (§242) |
| **Page titles** | static `index.html` title; never reflects route or resource | **[code]** | `MISSING` (§243) |
| Security headers | `main.py` — CSP (no `unsafe-eval`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP | **[code]** **[live]** | `PRODUCTION READY` (§178–§180) |
| Origin / CSRF guard | state-changing methods require an allow-listed `Origin`; 2 MB body cap | **[code]** | `PRODUCTION READY` (§169) |
| XSS posture | **zero** `dangerouslySetInnerHTML` in the entire frontend | **[code]** | `PRODUCTION READY` (§176) |
| Secret redaction | `security.py` central redaction; `pki.py` returns Secret **metadata only** | **[code]** **[live]** | `PRODUCTION READY` (§172, §173) |
| No external CDN | fonts/styles/scripts bundled; CSP `default-src 'self'` | **[code]** | `PRODUCTION READY` (§166, §167) |
| Read-only guard | `SUPERVISION [READ ONLY]` badge; the backend allowlist is authoritative | **[code]** | `GOOD` (§251–§253) |
| **Production indicator** | no production-profile concept | **[code]** | `MISSING` (§8) |
| Capability-driven nav | `NAV_SECTIONS` hardcoded; `/api/v1/capabilities` unused | **[code]** | `INCONSISTENT` (§137) |
| **Density modes** | fixed `rowHeight = 36` | **[code]** | `MISSING` (§27) |
| **Saved views** | none | **[code]** | `MISSING` (§245) |
| **Column persistence** | `columnVisibility` is component-local; lost on navigation | **[code]** | `PARTIAL` (§247) |
| Pins | `usePins` / `useAddPin` / `useRemovePin` wired | **[code]** | `GOOD` (§14) |
| History / recents | `useHistory` / `usePushHistory` wired; no recents UI surface | **[code]** | `PARTIAL` (§13) |
| **Reset preferences** | no action | **[code]** | `MISSING` (§333) |
| **Frontend unit tests** | 6 files / 30 tests — `lib/*` and 2 components only | **[code]** | `PARTIAL` (§183) |
| Backend unit tests | 230 tests, all passing | **[live]** | `PRODUCTION READY` |
| E2E tests | Playwright smoke + axe (`frontend/e2e/`) | **[code]** | `PARTIAL` (§291, §301) |
| **Visual regression** | none | **[code]** | `MISSING` (§216, §302) |

## 2. Shared component inventory

| Component | Purpose | Consumed by | STATUS |
| --- | --- | --- | --- |
| `DataTable` | TanStack Table + TanStack Virtual; sorting, global filter, column visibility, row virtualisation, CSV export, sticky header, `aria-sort`, row `tabIndex` | 10 feature pages | `GOOD` — no column pinning/resize, no density, no saved views, no server-side mode (§23, §25) |
| `common.tsx` | `StatusPill`, `ConfidenceTag`, `Freshness`, `PartialBanner`, `EmptyState`, `ErrorState`, `LoadingRows`, `RawView`, `Field`, `PageHeader` | everywhere | `PRODUCTION READY` — single shared vocabulary |
| `Inspector` | right-hand context panel: `useGraph` + `useImpact` + pin | `AppShell` | `GOOD` — fixed 340 px, `inspectorWidth` state exists but is unused by the panel (§123, §124) |
| `Sidebar`, `TopBar`, `StatusBar`, `Breadcrumbs`, `ThemeMenu` | shell chrome | `AppShell` | `GOOD` |
| `CommandPalette` | global search + navigation | `AppShell` | `PARTIAL` (see §1) |
| `ui/*` | `badge`, `button`, `card`, `dialog`, `input`, `select`, `tabs`, `primitives` (Tooltip/Skeleton/…) | everywhere | `GOOD` — Radix-backed where it matters |
| `LiveRefresher` | drives the LIVE interval | `AppShell` | `GOOD` |
| `Usage` | CPU/memory charts | `WorkloadsPage`, `PodDetailPage` | `GOOD` — no chart accessibility text alternative (§90) |

## 3. Per-route matrix

Shared columns are stated once: every table page inherits `DataTable` (sort,
filter, virtualisation, CSV export, sticky header, `aria-sort`), every page gets
`Freshness` + `PartialBanner` + `EmptyState` + `ErrorState` from `common.tsx`,
and all pages are keyboard-reachable through the shell. Deviations only are noted.

| Route | Feature | Source engine | Component | Working | Data complete | Live | Filter | Sort | Export | Evidence | STATUS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dashboard` | Overview | findings, workloads, pods, gitops, certificates, endpoint-gaps, storage | `DashboardPage` | ✅ **[live]** | ✅ | ✅ | n/a | n/a | ✗ | ✗ | `GOOD` — attention-first, domain state (no fake health score) (§15–§17) |
| `/findings` | Findings centre | `/findings` | `FindingsPage` | ✅ **[live]** | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ | `GOOD` — no lifecycle/fingerprint/filters-by-confidence (§44–§48) |
| `/workloads` | Pod inventory | `/workloads` | `WorkloadsPage` | ✅ **[live]** | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ | `GOOD` |
| `/workloads/pods/:name` | Pod detail | `/pods/{name}`, `/events`, `/logs`, `/metrics` | `PodDetailPage` | ✅ **[live]** | ✅ | ✅ | n/a | n/a | ✗ | ✗ | `PARTIAL` — no `/pods/{name}/dependencies` tab (§30–§33) |
| `/logs` | Log viewer | `/logs`, `/containers` | `LogsPage` | ✅ | ✅ | manual | ✅ | ✗ | ✅ | ✗ | `PARTIAL` — **no row virtualisation** (§92); no level filter or before/match/after context (§91, §94) |
| `/describe` | Resource describe | `/describe` | `DescribePage` | ✅ | ✅ | manual | ✅ | ✅ | ✅ | ✗ | `GOOD` |
| `/events` | Events timeline | `/events` | `EventsPage` | ✅ **[live]** | ✅ (433 rows cluster-wide **[live]**) | ✅ | ✅ | ✅ | ✅ | ✗ | `GOOD` — table-first, not timeline-first (§96) |
| `/health` | Engine health | `/health` | `ReportPage` | ✅ | ✅ | ✅ | n/a | n/a | ✅ | ✗ | `PARTIAL` — route exists but is **absent from navigation** (§9) |
| `/topology` | Dependency graph | `/graph/*`, `/graph/gitops`, `/impact/*` | `TopologyPage` (React Flow + Background/Controls/MiniMap) | ✅ | ✅ | ✅ | ✅ | n/a | ✗ | ✗ | `GOOD` — **no failure-path mode (§40), no blast-radius mode (§41), no edge evidence panel (§37), no domain filters (§39), no layout selector (§42)** |
| `/gitops` | GitOps | `/gitops` | `GitOpsPage` | ✅ **[live]** | ⚠️ summary only | ✅ | ✅ | ✅ | ✅ | ✗ | `PARTIAL` — `/gitops/sources`, `/kustomizations`, `/helmreleases`, `/chain`, `/{kind}/{name}/timeline` all **unwired** (§73–§78) |
| `/pki` | PKI / TLS | `/certificates`, `/secrets` | `PkiPage` | ✅ **[live]** | ⚠️ inventory only | ✅ | ✅ | ✅ | ✅ | ✗ | `SHALLOW` — no expiry dashboard, chain, consumers, duplicates, issuers or live TLS comparison (§66–§72) |
| `/network` | Network | `/network/services`, `/endpoint-gaps` | `NetworkPage` | ✅ **[live]** | ⚠️ partial | ✅ | ✅ | ✅ | ✅ | ✗ | `PARTIAL` — `/endpoints`, `/port-path/{service}`, `/policies/{pod}`, `/dns/{service}` **unwired** (§79–§84) |
| `/storage` | Storage | `/storage` | `StoragePage` | ✅ **[live]** | ⚠️ partial | ✅ | ✅ | ✅ | ✅ | ✗ | `PARTIAL` — `/storage/pvc/{name}`, `/consumers/{name}`, `/mount-warnings` **unwired**; no topology (§85, §86) |
| `/database` | Database | `/database`, `/database/services`, console | `DatabasePage`, `SqlConsole` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ | `GOOD` |
| `/kafka` | Messaging | `/kafka`, `/kafka/services`, `/kafka/topics` | `KafkaPage` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ | `GOOD` — broker reachability is an operator concern (§108) |
| `/application` | Application profile | `/application-profile` | `ReportPage` | ✅ | ✅ | ✅ | n/a | n/a | ✅ | ✗ | `GOOD` |
| `/incidents/:id` | Incident workspace | `/notes`, `/history`, `/evidence` | `IncidentPage` | ✅ | ✅ | ✅ | n/a | n/a | ✅ | ✅ | `GOOD` |
| `/baselines` | PRE / POST | `/baselines`, `/baselines/compare` | `BaselinePage` | ✅ | ✅ | manual | n/a | n/a | ✅ | ✅ | `GOOD` |
| `/evidence` | Evidence centre | `/evidence`, `/evidence/{id}`, `/evidence/{id}/file` | `EvidencePage` | ✅ | ✅ | manual | ✅ | ✅ | ✅ | ✅ | `GOOD` |
| `/exports` | Exports | `/exports/{domain}` | `ExportsPage` | ✅ | ✅ | n/a | n/a | n/a | ✅ | ✗ | `GOOD` |
| `/doctor` | Doctor / capabilities | `/doctor`, `/diagnostics` | `DoctorPage` | ✅ **[live]** | ✅ | ✅ | n/a | n/a | ✅ | ✗ | `GOOD` |
| `/settings` | Settings | `/settings`, `/connections*`, `/settings/live` | `SettingsPage` | ✅ **[live]** | ✅ | manual | n/a | n/a | ✗ | ✗ | `GOOD` |
## 4. Backend capability wiring gap register

**This is the most important result of the audit.** The backend already
implements deep, evidence-producing diagnostics. A large fraction of them are
never surfaced in the GUI, which is exactly the §290 violation
("NO CLI-ONLY HIGH-VALUE CAPABILITY") and the §286/§289 inversion: the engines
exist, the GUI simply does not reach them.

Nothing in this table needs new engine logic. Every row is an already-working,
already-tested HTTP route with **no frontend hook**.

| Route | What the engine already returns | GUI status | Spec |
| --- | --- | --- | --- |
| `GET /failure-path/{kind}/{name}` | the unhealthy dependency chain from source → workload → pod | **wired** — `/topology` failure-path mode, evidence-backed highlighting | §40 |
| `GET /impact/{kind}/{name}` | transitive consumers (blast radius) | **wired** — `/topology` blast-radius mode reverses the edges | §41 |
| `GET /path` | relationship path between two objects | **unwired** — needs a target picker | §36–§37 |
| `GET /graph/{kind}/{name}` | typed edges with evidence + confidence | **wired** — `/topology` plus a click-through edge-evidence panel | §36–§37, §347 |
| `GET /gitops/chain` | Source → Kustomization → HelmRelease → workload | **wired** — `/gitops` Flux chain, `/topology?graph=gitops` | §77 |
| `GET /gitops/{kind}/{name}/timeline` | reconciliation transitions per revision | **wired** — `/gitops` revision state, with a LAGGING badge | §78 |
| `GET /gitops/sources`, `/kustomizations`, `/helmreleases` | per-kind structured inventories | **wired via `/gitops`** — per-kind tabs read the same overview | §73–§76 |
| `GET /gitops/{kind}/{name}` | single GitOps object detail | **wired** — `/gitops` workspace drawer | §75 |
| `GET /certificates/expiry` | expiry distribution buckets | **wired** — `/pki` expiry posture, from the engine's own thresholds | §66–§67 |
| `GET /certificates/duplicates` | duplicate certificates | **wired** — `/pki` duplicate subjects | §66 |
| `GET /certificates/issuers` | issuer inventory | **wired** — `/pki` issuer list | §66 |
| `GET /certificates/{name}` | certificate detail | **wired** — `/pki` workspace drawer | §69 |
| `GET /certificates/{name}/chain` | leaf → intermediate → root trust chain | **wired** — `/pki` trust chain, with truncation stated | §71 |
| `GET /certificates/{name}/consumers` | which objects consume the certificate | **wired** — `/pki` consumers | §69 |
| `POST /tls/inspect` | live endpoint TLS vs Secret comparison | **BLOCKED by design** — the browser must not open arbitrary sockets; `/pki` states this and shows the Secret-side fingerprint instead | §72 |
| `GET /network/endpoints` | EndpointSlice detail | **wired** — `/network` EndpointSlices tab | §79 |
| `GET /network/port-path/{service}` | Ingress → Service → EndpointSlice → Pod → port | **wired** — `/network` Service drawer | §81, §82 |
| `GET /network/policies/{pod}` | ingress/egress isolation + selecting policies | **wired** — `/network` Network policies tab | §84 |
| `GET /network/dns/{service}` | service DNS, resolved IP, expected IP | **wired** — `/network` Service drawer, says NOT PROBED rather than guessing | §83 |
| `GET /storage/pvc/{name}` | PVC detail + binding chain | **wired** — `/storage` claim drawer | §86 |
| `GET /storage/consumers/{name}` | which pods mount the claim | **wired** — `/storage` claim drawer | §86 |
| `GET /storage/mount-warnings` | mount/attach anomalies | **wired** — `/storage` Mount warnings tab, split into unhealthy vs unconsumed | §85 |
| `GET /pods/{name}/dependencies` | pod-level dependency edges | **wired via `/graph/Pod/{name}`** — same engine operation, rendered by `/topology` | §33 |
| `GET /workloads/{kind}/{name}` | workload detail | **unwired** — reached through the inspector instead | §30 |
| `GET /pods/{name}/containers` | container list per pod | superseded by `/containers` | §91 |
| `GET /triage` | engine triage report | **unwired** — `/findings` renders the same findings | §44 |
| `GET /search` | server-side resource search | **wired** — palette → server search across 6 domains | §11, §12 |
| `GET /capabilities` | capability registry | **unwired** — `/doctor` reports tool availability | §137 |
| `GET /session` | server-side session registry | **unwired** — no console surface | — |
| `GET /health` | engine health report | **unwired** — `/health` route renders a report page, not this endpoint | §55 |
| `GET /profile` | application profile summary | **unwired** | §289 |
| `GET /api/v1/live` (SSE) | server-push change stream | **unwired** — 0 `EventSource` in the frontend | §53 |
| `GET /api/v1/logs` (SSE) | server-push log stream | **unwired** | §91 |
| `POST /connections/import` | paste-a-kubeconfig | **unwired** (route exists, no UI) | — |

**Count: 74 of 89 unique route templates have a literal frontend consumer (83%).**
Of the 15 that do not, **5 are covered by a sibling route**, **1 is blocked by
design** (`POST /tls/inspect`), and **9 are genuinely open** (listed above with a
reason). `test_route_coverage.py` recomputes this ratio from source and fails if
a route loses its consumer or the allowlist goes stale, so the number in this
table cannot silently drift.

For comparison, at the start of this remediation **30 of 94 routes** had no
frontend consumer: the GUI was a *shallow* view of a deep engine, the opposite of
the target architecture in §286.

## 5. What must not regress

These are genuine strengths of the current build. Any redesign must preserve
them; several are better than a typical greenfield effort would produce:

1. **One status vocabulary** (`lib/status.ts`) used by every page — no per-page colours.
2. **Icon + text + colour** for every status; colour is never the sole carrier.
3. **`Freshness` + `PartialBanner` + `EmptyState` + `ErrorState`** as shared primitives, including "next safe action" and raw evidence.
4. **TanStack Table + TanStack Virtual** already powering 10 pages — the §23/§24 requirement is largely met.
5. **React Flow** already used for topology with `Background`/`Controls`/`MiniMap`.
6. **Centralised design tokens** across 8 themes, dark and light both fully specified.
7. **Zero `dangerouslySetInnerHTML`**, a restrictive CSP with no `unsafe-eval`, `X-Frame-Options: DENY`, and an Origin-guarded state-changing surface.
8. **Secret metadata only** from the PKI routes; central redaction in `security.py`.
9. **SSE endpoints already exist** server-side (the gap is purely client-side).
## 6. Remediation log — this pass

Recorded so the matrix above can be read as a before/after rather than a
snapshot. Each item was verified against the running container.

| Item | Spec | Before | After | Evidence |
| --- | --- | --- | --- | --- |
| **Global search** | §11, §12 | `/api/v1/search` searched **Pods only** and was never called; the palette filtered 3 client-side datasets | Endpoint covers **6 domains** (Pod, Service, Certificate, GitOps, PVC, Finding) with the `pod:` `svc:` `cert:` `gitops:` `pvc:` `finding:` `ns:` `status:` grammar; palette calls it, debounced, with provenance per hit | **[live]** `redis` → 2 hits across 2 domains; `pod:` → 1 domain, 4 hits; `ns:learnalgorithm` → 9 hits across 3 kinds |
| **Route error isolation** | §131 | none — one throw blanked the console | `ErrorBoundary` around the route outlet, keyed on pathname; shell, scope and palette survive | **[code]** |
| **Code splitting** | §148, §149 | one 941 kB / **285.8 kB gzip** bundle; React Flow always parsed | 23 route chunks; initial JS **562.8 kB / 175.6 kB gzip (−38.6 %)**; React Flow moved to a lazy `TopologyPage` chunk (191.6 kB / 62.7 kB gzip) | **[live]** chunks served HTTP 200 |
| **Retry policy** | §144 | blanket `retry: 1` — retried 400/403/404 | retries only transport failures; 400/403/404 never retried | **[code]** |
| **Shortcut help** | §127 | `?` opened the palette | `?` opens a real keyboard reference (global, chords, search prefixes); palette footer links to it | **[code]** |
| **Keyboard chords** | §126 | `g d/p/l/x/g/c/n/s/f/t/e` | adds `g o/w/b/v/h/i` and `r` = refresh-now | **[code]** |
| **Page titles** | §243 | static `index.html` title | `Deployment/redis · DevOpsSentinel`-style title per route, from the breadcrumb trail | **[code]** |
| **Recents** | §13 | none | local `dsweb.recents` index surfaced in the palette; coordinates only, never contents | **[code]** |
| **Search accessibility** | §21, §186 | no live region for results | `aria-live` status announcing result count, domains searched and domains unavailable | **[code]** |
| **Partial-result honesty** | §59, §140 | silent | a domain that fails is reported in `unavailable` and named in the live region | **[code]** |

Still open from the gap register: the **9 genuinely unwired routes** (listed with
reasons in §4) — `GET /path`, `GET /triage`, `GET /capabilities`, `GET /session`,
`GET /health`, `GET /profile`, `GET /workloads/{kind}/{name}`,
`POST /connections/import`, and the `GET /live` SSE stream (§53).

## 7. Remediation log — deep-diagnostic routes

Second pass. Same rule as the first: every value shown is read from an engine
report; no diagnostic logic was added to the frontend (§286, §289, §290).

| Item | Spec | Before | After | Evidence |
| --- | --- | --- | --- | --- |
| **Graph edge evidence** | §37, §347 | the parser read `Kind/a -> Kind/b` edges and **discarded the report line**, so the GUI could show a relationship but never why it exists | `GraphEdge.evidence` carries the engine's own statement (bounded to 300 chars); clicking an edge opens a panel with kind, confidence, evidence and source | **[code]** `test_dependency_graph_edge_keeps_engine_evidence`, `test_graph_edges_carry_engine_evidence` |
| **Failure-path mode** | §40 | a client-side filter that hid healthy nodes, which is not the same as the engine's failure path | `/topology` asks `/failure-path/{kind}/{name}`; only nodes the **engine** marked unhealthy are highlighted, and the panel says so when there are none | **[code]** `test_failure_path_returns_typed_graph_and_marks_only_reported_nodes` |
| **Blast radius as a graph mode** | §41 | reverse dependencies existed only as a list in the inspector | `/topology` mode that follows the engine's edges backwards from the selected object, with a consumer count | **[code]** `test_impact_reports_reverse_dependencies_with_confidence` |
| **Layout control** | §42 | one hard-coded left-to-right layout | horizontal/vertical selector; layout is deterministic, so a refresh never shuffles the picture | **[code]** |
| **Certificate workspace** | §69–§72 | a flat inventory table; detail, chain and consumers were `curl`-only | `/pki` drawer with a validity timeline, identity, SANs, trust chain, consumers, and an explicit statement of why live TLS comparison stays engine-side | **[code]** `test_certificate_detail_pairs_inventory_row_with_its_graph`, `test_certificate_chain_walks_only_issuers_the_engine_reported` |
| **Trust-chain honesty** | §71 | — | the walk is cycle-guarded, and `complete` is true **only** when it reached a root; stopping because the issuer is not in the inventory is reported as truncated | **[code]** `test_certificate_chain_terminates_on_a_cycle` |
| **Engine expiry thresholds** | §66, §286 | expiry buckets were recomputed in the browser, which risked disagreeing with the engine's own CRITICAL/WARNING/ATTENTION thresholds | the parser now reads the `--cert-expiry` audit table (`OBJECT`/`CN-SAN` columns), and `/pki` takes its posture from that report — falling back to the inventory only when it is unavailable, and labelling the fallback | **[code]** `test_cert_expiry_audit_table_is_parsed` |
| **GitOps workspace** | §73–§78 | inventory table + a static chain list | per-kind tabs, plus a drawer with the managed chain (edge evidence) and revision state, badged LAGGING when desired ≠ applied | **[code]** `test_gitops_timeline_states_what_the_engine_observed` |
| **Network depth** | §79–§84 | services and endpoint gaps only | EndpointSlices tab, Network-policies tab, and a Service drawer with the port path and DNS record | **[code]** `test_service_dns_reports_the_record_without_claiming_a_probe`, `test_pod_policies_reports_configuration_not_runtime_permission` |
| **Storage depth** | §85–§86 | a flat PVC table | Mount warnings tab splitting unhealthy from unconsumed claims, plus a claim drawer with the binding chain and consumers | **[code]** `test_storage_mount_warnings_separate_unhealthy_from_unconsumed`, `test_pvc_detail_pairs_the_claim_with_its_binding_chain` |
| **Route-coverage guard** | §286, §288 | the gap was measured once, by hand | `test_route_coverage.py` recomputes the ratio from source and fails if a route loses its consumer or the allowlist goes stale | **[code]** 74/89 routes consumed (83%) |

### 7.1 Two silent-data-loss defects found by live verification

Both were found only by comparing the console against the real engine — the
tests passed and the pages looked correct while showing nothing.

| Defect | Spec | What was wrong | Fix | Evidence |
| --- | --- | --- | --- | --- |
| **GitOps chain parsed to zero edges** | §34, §77 | the engine reports its GitOps graph as a *tree* (`GitRepository/x` then `├── Kustomization/x`), but `normalize_dependency_graph` only understood `Kind/a -> Kind/b` arrows. The console therefore said *"no Flux chain was reported"* while the engine had reported one — a wrong statement, not an empty view | the parser now reads tree lines too, keyed by indent depth, so a child attaches to its own parent. The `Kind/name` match is anchored after the glyph prefix so the engine's own note (`sourceRef/status.inventory`) cannot be mistaken for a resource | **[live]** `/gitops/chain` went from **nodes=0 edges=0** (silently empty) to **nodes=4 edges=2**, each edge carrying its report line; `test_dependency_graph_reads_the_engine_tree_format` |
| **`FAIL=0` produced three findings** | §44, §286 | when nothing is wrong the engine emits a counter summary (`FAIL=0 WARN=0 …`) and an exit-code legend. The findings fallback read each line's severity token as a finding, so the queue showed **3 rows** while the engine reported nothing wrong | the fallback now skips counter lines (`FAIL=0`), legend lines (`0=no FAIL`), and meta commentary (`full detail:`, `data gaps`), while still accepting genuine embedded findings such as `[FAIL] Pod/x is not Ready` | **[live]** `/findings` went from **3 rows** to **0 rows** with `status=OK`; `test_normalize_findings_ignores_summary_and_legend_lines` |

Both are recorded here because they are the class of bug the spec's honesty
requirements exist to prevent: a console that renders a confident, wrong answer.
The general lesson is in §7.2.

### 7.2 Verification rule adopted

A route is not "wired" when a page renders. It is wired when the page **agrees
with the engine on a real cluster**, including on the empty case. Every route
closed in this pass was exercised against `vcluster-docker_dev`:

| Route | Live result |
| --- | --- |
| `/graph/Pod/{name}` | 1 edge with `EVIDENCE: Pod/… -> ReplicaSet/… -> Deployment/…` — the engine's own line |
| `/failure-path/Pod/{name}` | 3 nodes, 0 unhealthy, `healthSource` stated; nodes left `UNKNOWN` rather than assumed healthy |
| `/impact/Pod/{name}` | `count=0` with `confidence=HIGH CONFIDENCE` |
| `/network/endpoints` | 4 Services, first `ready=1` |
| `/network/dns/{service}` | `learnalgorithm-backend.learnalgorithm.svc.cluster.local`, `resolves=VERIFIED` |
| `/storage/mount-warnings` | `total=1`, `warnings=0`, `unconsumed=0` |
| `/storage/pvc/{name}` | claim `Bound`, `severity=OK` |
| `/gitops/sources` | 2 GitRepositories, `status=WARNING` |
| `/gitops/{kind}/{name}/timeline` | 1 entry, `lagging=True` — the repository has a desired revision and no applied one |
| `/findings` | 0 rows, `status=OK` (after the fix above) |

**Net effect:** 23 routes gained a frontend consumer and 1 was reclassified from
`API ONLY` to `BLOCKED`, moving the parity table from **28 `PARITY` / 29
`API ONLY`** to **46 `PARITY` / 3 `API ONLY`** (`GUI_CLI_PARITY.md` §8). Two
silent-data-loss defects found during live verification were fixed (§7.1).
Backend suite: **230 tests pass**. Frontend: **30 tests pass**, typecheck clean.
Initial bundle unchanged at **176.0 kB gzip**, because every new surface lives in
a lazy route chunk. Image `devopssentinel-web:1.2.8`, verified healthy against
`vcluster-docker_dev`.
### 7.3 Automatic cluster connection

The console is expected to find the cluster itself. Before this pass the
connection was fully manual, and the "Auto-detect" button could not succeed in
the container case at all.

| Item | Before | After | Evidence |
| --- | --- | --- | --- |
| **Detecting a WSL / vcluster cluster** | `auto_detect()` probed each kubeconfig's **own** server. A vcluster names `https://localhost:10093` — the `vcluster connect` port-forward — which inside a container is the container itself, so detection always failed and the operator had to discover → pair → activate by hand | `auto_connect()` pairs discovered host endpoints with discovered credentials: it re-probes each endpoint that answered `/version` using the kubeconfig, with a `server_override` and TLS-skip (the certificate is issued for `localhost`, not `host.docker.internal`), then falls back to each kubeconfig's own server | **[live]** fresh container, empty state → `active = vcluster-docker_dev`, `serverOverride = https://host.docker.internal:11259`, `serverVersion = v1.30.4`, 4 pods `source=LIVE` |
| **Connecting without being asked** | nothing ran until the operator pressed a button | `_autoconnect` runs as a background task at startup (off the request path), and `useAutoConnectOnLoad` calls `/connections/auto` once per page load when the connection is missing or dead. Neither replaces a connection that works | **[live]** `POST /connections/auto` → `ALREADY_CONNECTED`, 0 attempts, working connection untouched |
| **Telling "connected" from "configured"** | Settings said *connected* whenever `active.json` existed. A pinned override goes stale when the cluster restarts and the published port moves, so every page rendered empty while Settings insisted otherwise | `/connections` reports `health` separately from `active`, with `reachable`, `reason`, `detail`, `server` and `serverVersion`. The top bar shows the context when reachable and **UNREACHABLE** with a Connect button when not | **[live]** dead override `:19999` → `reachable=false reason=UNREACHABLE`; `/connections/auto` re-detected `:11259` → `reachable=true v1.30.4`, 4 pods LIVE |
| **Explaining a failed connection** | a single canned string, "no kubeconfig could authenticate", for every cause | every endpoint/credential pairing is reported in `attempts[]` with its own `reason` and `detail`, and `/settings` lists them | **[code]** `test_auto_connect_reports_why_every_pairing_failed` |
| **A button that reflects reality** | every detected endpoint showed the same blue **Connect**, including the one already in use — so a working connection looked like it still needed pressing, and there was no way to tell the live endpoint from the decoys that answer `/version` anonymously | the button is a toggle: **Connect** (blue) becomes **Disconnect** (green) once connected, and a green `connected` badge with a check icon sits inside the row. The active context row behaves the same, or offers **Reconnect** when the saved endpoint has gone stale. Matching is by `host:port` (new `lib/endpoint.ts`), because the discovery list and a saved override spell the same address differently | **[code]** `sameEndpoint` (6 tests); **[live]** `Connect → Disconnect → Connect`, `ALREADY_CONNECTED` on the healthy path, 4 pods live |
| **An explicit Disconnect that sticks** | not applicable before — nothing connected automatically | auto-connect would have undone a deliberate Disconnect on the next page load, making the button look broken. An explicit disconnect is now remembered (`lib/autoConnect.ts`, `localStorage`) and auto-connect respects it until a connection is asked for again | **[code]** `autoConnect.test.ts` (4 tests) |

Backend suite: **263 tests pass**. Frontend: **64 tests pass**. Initial bundle
**176.93 kB gzip**. Image `devopssentinel-web:1.3.7`.

### 7.4 Native (non-container) validation on WSL Ubuntu

The auto-detect path was written for the container case and had only ever been
exercised there. Running the utility natively on WSL Ubuntu — no container —
found a real defect, because the right host to probe depends on where the app
runs.

**Environment.** WSL2 Ubuntu, Python 3.12.3, `kubectl` v1.30.4, Docker socket
present and readable, `~/.kube/config` naming `https://localhost:10093`. The
vcluster publishes `0.0.0.0:11259 -> 8443/tcp`. `/.dockerenv` is absent and
`/proc/1/cgroup` is `0::/init.scope`, so the app is **not** in a container.

**What the environment showed:**

| Endpoint | Result |
| --- | --- |
| `https://127.0.0.1:11259` (loopback) | **works** — `v1.30.4` |
| `https://localhost:10093` (the kubeconfig's own server) | **401** — answers `/version` anonymously, rejects the client certificate |
| `https://192.168.1.15:11259` (`host.docker.internal` on this host) | **blocked** by the Windows firewall |
| `https://172.28.208.1:11259` (WSL default gateway) | works |

**Defect found.** `_docker_hosts()` returned only `host.docker.internal`,
`gateway.docker.internal` and the default gateway — **loopback was never
probed**. Running natively that meant:

* the Docker-derived endpoint (`host.docker.internal`) was firewalled and failed,
* `127.0.0.1:11259` was correct but never tried,
* so the sweep fell through to the **default gateway**, and the app connected
  by routing every API call out of WSL to Windows and back.

It did connect — `health.reachable = true`, 4 pods live — which is exactly why
this was worth finding: it looked correct while taking a needless detour that
depends on the Windows firewall staying open.

**Fix.**

| Change | Why |
| --- | --- |
| `discovery.in_container()` | `/.dockerenv` or a Docker/containerd cgroup marker. Decides which host is most likely correct |
| `discovery._sweep_hosts()` | loopback first when native, omitted when in a container (`127.0.0.1` there is the container itself) |
| `discovery._from_docker()` | a published port is on loopback natively, on the Docker host in a container |
| `discovery._endpoint_rank()` | order: Docker evidence → loopback on a native run → everything else |
| `connections._endpoint_key()` | `localhost` / `127.0.0.1` / `::1` collapse to one host, so the credentials that already name the right port are preferred |

Both host lists are still swept and only endpoints that answer `/version`
survive, so guessing wrong costs one probe and nothing else — which is why the
container case is unaffected.

**Before / after, same machine, same cluster:**

| | Before | After |
| --- | --- | --- |
| Endpoints probed | 30 | 48 |
| Endpoints found | 1 | **5** |
| Chosen override | `https://172.28.208.1:11259` (via Windows) | **`https://127.0.0.1:11259`** (loopback) |
| Kubeconfig paired | `~/.kube/config` (names port 10093) | `~/.kube/dev.kubeconfig` (names port 11259) |

**Verified natively end to end:**

| Check | Result |
| --- | --- |
| Startup auto-connect, empty state | `active = vcluster-docker_dev`, override `https://127.0.0.1:11259`, `v1.30.4` |
| `POST /connections/auto` | `ALREADY_CONNECTED`, 0 attempts — working connection untouched |
| SPA served | `/`, `/settings`, `/topology` → HTTP 200 |
| Live data | pods 4, workloads 4, services 4, storage 1 — all `status=OK` |
| Real rows | `postgres-0`, `redis-5d66f5d4b6-ct9xs`, backend/frontend all `OK 1/1` |
| Container case unchanged | rebuilt `1.3.1`, still picks `https://host.docker.internal:11259`, 4 pods live |

**Test coverage:** 13 new tests — `test_discovery.py` (12: container detection,
sweep hosts, Docker-derived hosts, ranking) and a loopback-collapse test for
`_endpoint_key`. Backend suite: **251 tests pass**.

**Note on running natively.** This machine has no `python3-venv` and no
passwordless sudo, so the run used `pip install --target ~/dsweb-libs` with
`PYTHONPATH` instead of a venv. A venv is the documented path and works the same
where `python3-venv` is installed.







