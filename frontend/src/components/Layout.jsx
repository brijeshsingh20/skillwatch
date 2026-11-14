import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Bell, Building2, FileBarChart, LayoutDashboard, LogOut, Menu, ShieldCheck, UploadCloud, Users, X } from "lucide-react";
import { ROLES, ROLE_LABELS, useAuth } from "../auth.jsx";
import LoginBackground from "./LoginBackground.jsx";
import Logo from "./Logo.jsx";


const NAV = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/centres", label: "Centres", icon: Building2 },
  { to: "/analyse", label: "Analyse footage", icon: UploadCloud, roles: [ROLES.SUPER, ROLES.OFFICER] },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/accuracy", label: "Accuracy report", icon: FileBarChart },
  { to: "/privacy", label: "Privacy note", icon: ShieldCheck },
  { to: "/users", label: "Users", icon: Users, roles: [ROLES.SUPER] },
];

export default function Layout() {
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false); // phone menu drawer
  const items = NAV.filter((n) => !n.roles || hasRole(...n.roles));

  // Close the drawer after navigating, and on Escape.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="flex min-h-screen">
      <LoginBackground behind />

      {open && <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={() => setOpen(false)} aria-hidden="true" />}

      {/* glass sidebar: fixed slide-in drawer on phones, sticky column from md up */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 max-w-[85vw] shrink-0 flex-col border-r border-cobalt-400/20 bg-midnight-950/90 text-slate-200 backdrop-blur-xl transition-[transform,visibility] duration-300 md:sticky md:inset-y-auto md:top-0 md:h-screen md:translate-x-0 md:bg-midnight-950/60 md:visible ${
          open ? "visible translate-x-0" : "invisible -translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-5 text-lg font-bold tracking-tight text-white">
          <span className="flex items-center gap-2.5">
            <Logo size={30} />
            SkillWatch AI
          </span>
          <button className="rounded-lg p-1 text-slate-300 hover:text-white md:hidden" aria-label="Close menu" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl border px-3 py-2 text-sm transition duration-200 ${
                  isActive
                    ? "border-cobalt-400/60 bg-cobalt/30 text-white shadow-glow"
                    : "border-transparent text-slate-300 hover:bg-cobalt/15 hover:text-white"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`h-4 w-4 ${isActive ? "text-acid" : ""}`} /> {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-cobalt-400/20 p-4 text-xs text-slate-400">
          <div className="mb-3 md:hidden">
            <div className="text-sm font-medium text-white">{user.full_name}</div>
            <div>{ROLE_LABELS[user.role]}</div>
          </div>
          Aggregate counts only. No faces, no identities.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* glass header */}
        <header className="sticky top-0 z-20 flex items-center justify-between gap-2 border-b border-cobalt-400/20 bg-midnight-950/50 px-3 py-3 backdrop-blur-xl sm:px-4">
          <button className="btn-secondary px-2.5 md:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu className="h-4 w-4" />
          </button>
          <div className="hidden text-sm text-slate-400 md:block">Training centre compliance monitoring</div>
          <div className="flex min-w-0 items-center gap-3">
            <div className="hidden min-w-0 text-right text-sm leading-tight sm:block">
              <div className="truncate font-medium text-white">{user.full_name}</div>
              <div className="truncate text-xs text-slate-400">{ROLE_LABELS[user.role]}</div>
            </div>
            <button
              className="btn-secondary"
              aria-label="Sign out"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              <LogOut className="h-4 w-4" /> <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-3 sm:p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
