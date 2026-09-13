import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/AuthContext";
import { RequireAuth } from "./lib/RequireAuth";
import { Login } from "./pages/Login";
import { Live } from "./pages/Live";
import { Compare } from "./pages/Compare";

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-accent" />
            <span className="font-semibold text-ink">CartPace</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <a href="/live" className="text-slate-600 hover:text-ink">
              Live
            </a>
            {user?.role === "supervisor" && (
              <a href="/compare" className="text-slate-600 hover:text-ink">
                Compare
              </a>
            )}
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
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/live"
          element={
            <RequireAuth>
              <Shell>
                <Live />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/compare"
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
