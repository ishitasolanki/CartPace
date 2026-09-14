import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/AuthContext";
import { RequireAuth } from "./lib/RequireAuth";
import { Login } from "./pages/Login";
import { Live } from "./pages/Live";
import { Compare } from "./pages/Compare";

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active = pathname.startsWith(to);
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={active ? "font-medium text-ink" : "text-slate-600 hover:text-ink"}
    >
      {children}
    </Link>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      {/* MUST: skip-to-content link (Web Interface Guidelines). Invisible
          until keyboard-focused, so it costs nothing for mouse/touch users. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
            <span className="font-semibold text-ink">CartPace</span>
          </div>
          <nav className="flex items-center gap-4 text-sm" aria-label="Main">
            <NavLink to="/live">Live</NavLink>
            {user?.role === "supervisor" && <NavLink to="/compare">Compare</NavLink>}
            <span className="text-slate-400">
              {user?.username} · {user?.role}
            </span>
            <button
              onClick={logout}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              Sign out
            </button>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/live/:runId?"
          element={
            <RequireAuth>
              <Shell>
                <Live />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/compare/:runId?"
          element={
            <RequireAuth role="supervisor">
              <Shell>
                <Compare />
              </Shell>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/live" replace />} />
      </Routes>
    </AuthProvider>
  );
}
