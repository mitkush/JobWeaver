import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, type Me } from "@/api/client";
import { useMe } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { PageSpinner } from "@/components/ui/spinner";
import { AdminSourcesPage } from "@/pages/AdminSourcesPage";
import { FactBankPage } from "@/pages/FactBankPage";
import { FeedPage } from "@/pages/FeedPage";
import { DraftPage } from "@/pages/DraftPage";
import { JobPage } from "@/pages/JobPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { PreferencesPage } from "@/pages/PreferencesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SignInPage } from "@/pages/SignInPage";

import { AppShell } from "./AppShell";

/** Signed-in area. Unfinished onboarding always comes first, except Settings. */
function Authenticated({ children }: { children: (me: Me) => ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <PageSpinner />;
  if (me.error instanceof ApiError && me.error.status === 401) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/sign-in?next=${next}`} replace />;
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-md p-8">
        <Alert tone="error" title="JobWeaver could not load">
          {me.error.message}
        </Alert>
      </div>
    );
  }
  const onboarding = me.data.onboarding.next_step !== "done";
  const allowed = location.pathname.startsWith("/onboarding") || location.pathname === "/settings";
  if (onboarding && !allowed) return <Navigate to="/onboarding" replace />;
  return <AppShell me={me.data}>{children(me.data)}</AppShell>;
}

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route path="/" element={<Navigate to="/feed" replace />} />
      <Route path="/onboarding/:step?" element={<Authenticated>{(me) => <OnboardingPage me={me} />}</Authenticated>} />
      <Route path="/feed" element={<Authenticated>{() => <FeedPage />}</Authenticated>} />
      <Route path="/jobs/:jobId" element={<Authenticated>{() => <JobPage />}</Authenticated>} />
      <Route path="/drafts/:draftId" element={<Authenticated>{() => <DraftPage />}</Authenticated>} />
      <Route path="/fact-bank" element={<Authenticated>{() => <FactBankPage />}</Authenticated>} />
      <Route path="/preferences" element={<Authenticated>{() => <PreferencesPage />}</Authenticated>} />
      <Route path="/settings" element={<Authenticated>{(me) => <SettingsPage me={me} />}</Authenticated>} />
      <Route
        path="/admin/sources"
        element={<Authenticated>{(me) => (me.role === "admin" ? <AdminSourcesPage /> : <NotFoundPage />)}</Authenticated>}
      />
      <Route path="*" element={<Authenticated>{() => <NotFoundPage />}</Authenticated>} />
    </Routes>
  );
}
