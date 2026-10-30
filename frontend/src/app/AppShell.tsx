import { Briefcase, LogOut, Moon, Sun } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import type { Me } from "@/api/client";
import { useSignOut } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { gmailConnectHref } from "@/features/gmail/links";
import { accentFor } from "@/lib/accent";
import { cn } from "@/lib/cn";

/** Sets the page accent on <html>, which re-tints every brand-* class and the glow. */
function usePageAccent() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.documentElement.dataset.accent = accentFor(pathname);
  }, [pathname]);
}

/** "[ FEED ]": brackets mark the active item, as on onebrain.run. They are hidden from
 * screen readers, which already announce the current page. */
function NavLabel({ label, active }: { label: string; active: boolean }) {
  return (
    <>
      <span aria-hidden className={cn("mr-1.5", !active && "invisible")}>[</span>
      {label}
      <span aria-hidden className={cn("ml-1.5", !active && "invisible")}>]</span>
    </>
  );
}

const NAV = [
  { to: "/feed", label: "Feed" },
  { to: "/applications", label: "Applications" },
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
  const location = useLocation();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const onboarding = me.onboarding.next_step !== "done";
  const nav = me.role === "admin" ? [...NAV, { to: "/admin/sources", label: "Sources" }] : NAV;
  usePageAccent();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-950/85">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-8 px-4 sm:px-6 lg:px-10">
          <Logo />
          {!onboarding && (
            <nav aria-label="Main" className="hidden flex-1 justify-center gap-2 lg:gap-5 md:flex">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to === "/feed" && location.pathname === "/feed" ? location.pathname + location.search : item.to}
                  className={({ isActive }) =>
                    cn(
                      "py-1.5 font-mono text-[11px] font-bold tracking-[0.24em] whitespace-nowrap uppercase transition-colors",
                      isActive
                        ? "text-accent-700 dark:text-accent-300 neon-cyan"
                        : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white",
                    )
                  }
                >
                  {({ isActive }) => <NavLabel label={item.label} active={isActive} />}
                </NavLink>
              ))}
            </nav>
          )}
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <span className="hidden font-mono text-[11px] text-slate-600 md:inline dark:text-slate-400">{me.email}</span>
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
          <nav aria-label="Main mobile" className="flex gap-4 overflow-x-auto px-4 pb-2 md:hidden">
            {nav.map((item) => (
              <NavLink key={item.to} to={item.to === "/feed" && location.pathname === "/feed" ? location.pathname + location.search : item.to} className="py-1 font-mono text-[11px] font-bold tracking-[0.18em] whitespace-nowrap text-slate-600 uppercase aria-[current=page]:text-accent-700 dark:text-slate-400 dark:aria-[current=page]:text-accent-300">
                {({ isActive }) => <NavLabel label={item.label} active={isActive} />}
              </NavLink>
            ))}
          </nav>
        )}
        {/* A thin accent-to-cyan line under the header. */}
        <div aria-hidden className="h-px bg-gradient-to-r from-transparent via-brand-500/60 to-transparent dark:via-brand-500 dark:to-accent-400/60" />
        <GmailBanner me={me} />
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10 lg:py-12">{children}</main>
    </div>
  );
}

/** "● JOBWEAVER // FACT_BANK": the boxed eyebrow onebrain.run puts above each section. */
function eyebrowFor(title: string) {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

/** Display heading with the last word in the page accent: outlined and glowing in the
 * dark theme, like "SECOND BRAIN." A single-word title stays solid so it reads clearly.
 * The words stay one text node apart, so the accessible name is unchanged. */
export function DisplayTitle({ title, className }: { title: string; className?: string }) {
  const words = title.trim().split(/\s+/);
  const last = words.pop() ?? "";
  return (
    <h1 className={cn("font-display text-4xl leading-[0.95] font-bold tracking-tight uppercase italic sm:text-5xl", className)}>
      {words.length > 0 && <>{words.join(" ")} </>}
      <span className={cn("text-brand-600 dark:text-brand-500", words.length > 0 ? "outline-text" : "neon-text")}>{last}</span>
    </h1>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow eyebrow-box mb-5" aria-hidden>
          <span className="size-1.5 rounded-full bg-brand-600 dark:bg-brand-500" />
          jobweaver <span className="text-slate-400 dark:text-slate-500">//</span> {eyebrowFor(title)}
        </p>
        <DisplayTitle title={title} />
        {description && <p className="mt-4 max-w-3xl font-mono text-sm leading-relaxed text-slate-600 dark:text-slate-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Logo({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <Link to="/" className="group flex items-center gap-2" aria-label="JobWeaver home">
      <span className={cn("clip-corner bg-brand-600 text-white dark:bg-brand-500 dark:text-slate-950", size === "lg" ? "p-1.5" : "p-1")}>
        <Briefcase className={size === "lg" ? "size-5" : "size-4"} aria-hidden />
      </span>
      <span className={cn("font-display font-bold tracking-wide uppercase italic", size === "lg" ? "text-xl" : "text-base")}>
        Job<span className="text-brand-600 dark:text-brand-500 neon-text">Weaver</span>
      </span>
    </Link>
  );
}
