import { lazy, Suspense, type ReactNode } from "react";
import { createHashRouter, Navigate, useLocation } from "react-router";
import { AppLayout } from "@/app-layout";
import { Skeleton } from "@/components/ui/skeleton";

// Each view loads on first visit; the shell (sidebar, header, dialogs) is always loaded.
const AuditPage = lazy(() => import("@/features/audit/audit-page").then((m) => ({ default: m.AuditPage })));
const KeywordsPage = lazy(() =>
  import("@/features/keywords/keywords-page").then((m) => ({ default: m.KeywordsPage })),
);
const OptimizePage = lazy(() =>
  import("@/features/optimize/optimize-page").then((m) => ({ default: m.OptimizePage })),
);
const CompetitorsPage = lazy(() =>
  import("@/features/competitors/competitors-page").then((m) => ({ default: m.CompetitorsPage })),
);
const PaidPage = lazy(() => import("@/features/paid/paid-page").then((m) => ({ default: m.PaidPage })));
const NichePage = lazy(() => import("@/features/niche/niche-page").then((m) => ({ default: m.NichePage })));

function View({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="grid gap-4 p-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

function RedirectHome() {
  const location = useLocation();
  return <Navigate to={`/audit${location.search}`} replace />;
}

// Hash routing: the Python server serves a single index.html with no fallback route.
export const router = createHashRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <RedirectHome /> },
      { path: "audit", element: <View><AuditPage /></View> },
      { path: "keywords", element: <View><KeywordsPage /></View> },
      { path: "optimize", element: <View><OptimizePage /></View> },
      { path: "competitors", element: <View><CompetitorsPage /></View> },
      { path: "paid", element: <View><PaidPage /></View> },
      { path: "niche", element: <View><NichePage /></View> },
      { path: "*", element: <RedirectHome /> },
    ],
  },
]);
