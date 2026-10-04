import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { isLiveKey } from "@/lib/live";
import { useApp } from "@/state/AppContext";

/**
 * Drives the LIVE interval configured in the top bar.
 *
 * The selector only stores the interval; this component is what actually
 * re-reads the mounted queries, which is why `LIVE 5 sec` used to look
 * decorative. `refetchQueries` is used instead of `invalidateQueries` because
 * a tick means "read it again now" and must bypass the 15 s `staleTime`.
 *
 * The interval fires once on activation too, so switching from OFF to 5 s
 * refreshes immediately instead of after a silent 5 s wait. `liveActive` is
 * already false while the tab is hidden (see AppContext), so a backgrounded
 * tab stops polling and refreshes once on return.
 */
export function LiveRefresher() {
  const queryClient = useQueryClient();
  const { live, liveActive } = useApp();

  useEffect(() => {
    if (!liveActive) return;
    const tick = () =>
      void queryClient.refetchQueries({
        type: "active",
        predicate: (query) => isLiveKey(query.queryKey),
      });
    tick();
    const timer = window.setInterval(tick, live * 1000);
    return () => window.clearInterval(timer);
  }, [queryClient, live, liveActive]);

  return null;
}
