import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { EmptyState, LoadingRows } from "@/components/common";
import { TooltipProvider } from "@/components/ui/primitives";
import { AppProvider } from "@/state/AppContext";

/**
 * Route-level code splitting (spec sections 148-149).
 *
 * The dependency graph, log viewer and observability views are the heavy ones,
 * and React Flow alone is a large part of the bundle. Splitting per route keeps
 * the initial shell small and means a page the operator never opens is never
 * parsed or evaluated.
 */
const DashboardPage = lazy(() =>
  import("@/features/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const WorkloadsPage = lazy(() =>
  import("@/features/workloads/WorkloadsPage").then((m) => ({ default: m.WorkloadsPage })),
);
const PodDetailPage = lazy(() =>
  import("@/features/workloads/PodDetailPage").then((m) => ({ default: m.PodDetailPage })),
);
const LogsPage = lazy(() => import("@/features/logs/LogsPage").then((m) => ({ default: m.LogsPage })));
const DescribePage = lazy(() =>
  import("@/features/describe/DescribePage").then((m) => ({ default: m.DescribePage })),
);
const EventsPage = lazy(() =>
  import("@/features/events/EventsPage").then((m) => ({ default: m.EventsPage })),
);
const ReportPage = lazy(() =>
  import("@/features/reports/ReportPage").then((m) => ({ default: m.ReportPage })),
);
const TopologyPage = lazy(() =>
  import("@/features/topology/TopologyPage").then((m) => ({ default: m.TopologyPage })),
);
const GitOpsPage = lazy(() =>
  import("@/features/gitops/GitOpsPage").then((m) => ({ default: m.GitOpsPage })),
);
const PkiPage = lazy(() => import("@/features/pki/PkiPage").then((m) => ({ default: m.PkiPage })));
const NetworkPage = lazy(() =>
  import("@/features/network/NetworkPage").then((m) => ({ default: m.NetworkPage })),
);
const StoragePage = lazy(() =>
  import("@/features/storage/StoragePage").then((m) => ({ default: m.StoragePage })),
);
const DatabasePage = lazy(() =>
  import("@/features/database/DatabasePage").then((m) => ({ default: m.DatabasePage })),
);
const KafkaPage = lazy(() =>
  import("@/features/kafka/KafkaPage").then((m) => ({ default: m.KafkaPage })),
);
const FindingsPage = lazy(() =>
  import("@/features/findings/FindingsPage").then((m) => ({ default: m.FindingsPage })),
);
const IncidentPage = lazy(() =>
  import("@/features/incidents/IncidentPage").then((m) => ({ default: m.IncidentPage })),
);
const BaselinePage = lazy(() =>
  import("@/features/baselines/BaselinePage").then((m) => ({ default: m.BaselinePage })),
);
const EvidencePage = lazy(() =>
  import("@/features/evidence/EvidencePage").then((m) => ({ default: m.EvidencePage })),
);
const ExportsPage = lazy(() =>
  import("@/features/exports/ExportsPage").then((m) => ({ default: m.ExportsPage })),
);
const DoctorPage = lazy(() =>
  import("@/features/doctor/DoctorPage").then((m) => ({ default: m.DoctorPage })),
);
const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry only transport-shaped failures. An RBAC denial, a 404 or a bad
      // request will never succeed on a second attempt (spec section 144).
      retry: (failureCount, error) => {
        const status = (error as { status?: number } | null)?.status ?? 0;
        if (status === 400 || status === 403 || status === 404) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

function NotFoundPage() {
  return (
    <EmptyState
      kind="UNAVAILABLE"
      title="Route not found"
      detail="The requested route does not exist in DevOpsSentinel Web. Press Ctrl K to search resources and commands."
    />
  );
}

/** Structural placeholder, not a centred spinner (spec sections 60, 189). */
function RouteFallback() {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Loading view</span>
      <LoadingRows rows={8} />
    </div>
  );
}

export function App() {
  return (
    <AppProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <BrowserRouter>
            <Suspense fallback={<RouteFallback />}>
              <Routes>
                <Route element={<AppShell />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/workloads" element={<WorkloadsPage />} />
                <Route path="/workloads/pods/:name" element={<PodDetailPage />} />
                <Route path="/logs" element={<LogsPage />} />
                <Route path="/describe" element={<DescribePage />} />
                <Route path="/events" element={<EventsPage />} />
                <Route path="/health" element={<ReportPage kind="health" />} />
                <Route path="/topology" element={<TopologyPage />} />
                <Route path="/gitops" element={<GitOpsPage />} />
                <Route path="/pki" element={<PkiPage />} />
                <Route path="/network" element={<NetworkPage />} />
                <Route path="/storage" element={<StoragePage />} />
                <Route path="/database" element={<DatabasePage />} />
                <Route path="/kafka" element={<KafkaPage />} />
                <Route path="/application" element={<ReportPage kind="application" />} />
                <Route path="/findings" element={<FindingsPage />} />
                <Route path="/incidents/:id" element={<IncidentPage />} />
                <Route path="/baselines" element={<BaselinePage />} />
                <Route path="/evidence" element={<EvidencePage />} />
                <Route path="/exports" element={<ExportsPage />} />
                <Route path="/doctor" element={<DoctorPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AppProvider>
  );
}