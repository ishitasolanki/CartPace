import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { usePageTitle } from "../lib/usePageTitle";
import { Spinner } from "../components/Spinner";

export function Login() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate("/live");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-accent" />
          <h1 className="text-2xl font-bold text-ink">CartPace</h1>
          <p className="mt-1 text-sm text-slate-500">
            Cartridge allocation controller
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label
            htmlFor="username"
            className="mb-1 block text-sm font-medium text-slate-700"
          >
            Username
          </label>
          <input
            id="username"
            name="username"
            className="mb-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-base outline-none focus:border-accent focus:ring-1 focus:ring-accent sm:text-sm"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
          />

          <label
            htmlFor="password"
            className="mb-1 block text-sm font-medium text-slate-700"
          >
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            className="mb-5 w-full rounded-lg border border-slate-300 px-3 py-2 text-base outline-none focus:border-accent focus:ring-1 focus:ring-accent sm:text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />

          {error && (
            <p
              role="alert"
              className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="motion-safe:transition flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && <Spinner className="text-white" />}
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}
