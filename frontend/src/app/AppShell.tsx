import { Briefcase, LogOut, Moon, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import type { Me } from "@/api/client";
import { useSignOut } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { gmailConnectHref } from "@/features/gmail/links";
import { cn } from "@/lib/cn";

const NAV = [
  { to: "/feed", label: "Feed" },
  { to: "/fact-bank", label: "Fact Bank" },
  { to: "/preferences", label: "Preferences" },
  { to: "/settings", label: "Settings" },
];

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  function toggle() {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("jw-theme", next ? "dark" : "light");
    } catch {
      // Private mode: the choice just is not remembered.
    }
    setDark(next);
  }
  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label={dark ? "Use light theme" : "Use dark theme"}>
      {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </Button>
  );
}

function GmailBanner({ me }: { me: Me }) {
  if (me.gmail.state !== "expires_soon" && me.gmail.state !== "expired") return null;
  const expired = me.gmail.state === "expired";
  return (
    <Alert
      tone={expired ? "error" : "warning"}
      className="rounded-none border-x-0 border-t-0"
      action={
        <a className={buttonClasses("secondary", "sm")} href={gmailConnectHref(location.pathname)}>
          Reconnect Gmail
        </a>
      }
    >
      {expired
        ? "Gmail access ended. Reconnect before opening drafts in Gmail."
        : "Gmail access ends within a day. Reconnect now so opening drafts in Gmail keeps working."}
    </Alert>
  );
}

export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const signOut = useSignOut();
  const navigate = useNavigate();
  const onboarding = me.onboarding.next_step !== "done";
  const nav = me.role === "admin" ? [...NAV, { to: "/admin/sources", label: "Sources" }] : NAV;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <span className="rounded-md bg-brand-600 p-1 text-white">
              <Briefcase className="size-4" aria-hidden />
            </span>
            JobWeaver
          </Link>
          {!onboarding && (
            <nav aria-label="Main" className="hidden gap-1 sm:flex">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-3 py-1.5 text-sm font-medium",
                      isActive
                        ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white"
                        : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-sm text-slate-600 md:inline dark:text-slate-400">{me.email}</span>
            <ThemeToggle />
            <Button
              variant="ghost"
              size="sm"
              aria-label="Sign out"
              onClick={async () => {
                await signOut.mutateAsync();
                navigate("/sign-in");
              }}
            >
              <LogOut className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
        {!onboarding && (
          <nav aria-label="Main mobile" className="flex gap-1 overflow-x-auto px-4 pb-2 sm:hidden">
            {nav.map((item) => (
              <NavLink key={item.to} to={item.to} className="rounded-md px-3 py-1 text-sm whitespace-nowrap aria-[current=page]:bg-slate-100 dark:aria-[current=page]:bg-slate-800">
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
        <GmailBanner me={me} />
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}
