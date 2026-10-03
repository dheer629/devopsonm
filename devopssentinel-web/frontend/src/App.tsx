import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/common";
import { TooltipProvider } from "@/components/ui/primitives";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { DoctorPage } from "@/features/doctor/DoctorPage";
import { EvidencePage } from "@/features/evidence/EvidencePage";
import { EventsPage } from "@/features/events/EventsPage";
import { FindingsPage } from "@/features/findings/FindingsPage";
import { GitOpsPage } from "@/features/gitops/GitOpsPage";
import { NetworkPage } from "@/features/network/NetworkPage";
import { PkiPage } from "@/features/pki/PkiPage";
import { ReportPage } from "@/features/reports/ReportPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StoragePage } from "@/features/storage/StoragePage";
import { TopologyPage } from "@/features/topology/TopologyPage";
import { PodDetailPage } from "@/features/workloads/PodDetailPage";
import { WorkloadsPage } from "@/features/workloads/WorkloadsPage";
import { AppProvider } from "@/state/AppContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
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
      detail="The requested route does not exist in DevOpsSentinel Web."
    />
  );
}

export function App() {
  return (
    <AppProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<AppShell />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/workloads" element={<WorkloadsPage />} />
                <Route path="/workloads/pods/:name" element={<PodDetailPage />} />
                <Route path="/events" element={<EventsPage />} />
                <Route path="/health" element={<ReportPage kind="health" />} />
                <Route path="/topology" element={<TopologyPage />} />
                <Route path="/gitops" element={<GitOpsPage />} />
                <Route path="/pki" element={<PkiPage />} />
                <Route path="/network" element={<NetworkPage />} />
                <Route path="/storage" element={<StoragePage />} />
                <Route path="/database" element={<ReportPage kind="database" />} />
                <Route path="/kafka" element={<ReportPage kind="kafka" />} />
                <Route path="/etdp" element={<ReportPage kind="etdp" />} />
                <Route path="/findings" element={<FindingsPage />} />
                <Route path="/evidence" element={<EvidencePage />} />
                <Route path="/doctor" element={<DoctorPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AppProvider>
  );
}