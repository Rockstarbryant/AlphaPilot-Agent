"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { setSession } from "@/lib/use-user";
import { Button } from "@/components/ui";

export default function LoginPage() {
  return <Suspense fallback={null}><LoginPageInner /></Suspense>;
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const expired = searchParams.get("expired") === "1";
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      setSession(result.user_id, result.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="text-gold text-lg tracking-wide">ALPHAPILOT</div>
          <div className="text-sm text-muted mt-1">Find opportunities. Control risk. Optimize capital.</div>
        </div>

        <form onSubmit={handleSubmit} className="border border-line bg-surface rounded-sm p-5 space-y-4">
          {expired && (
            <div className="text-xs text-gold border border-gold/40 bg-gold/5 rounded-sm p-2">
              Your session expired — log in again to continue.
            </div>
          )}
          <div>
            <label className="block text-xs text-muted mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-surface-raised border border-line rounded-sm px-3 py-2 text-sm outline-none focus:border-gold"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface-raised border border-line rounded-sm px-3 py-2 text-sm outline-none focus:border-gold"
            />
          </div>

          {error && <div className="text-xs text-loss">{error}</div>}

          <Button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </Button>

          <div className="text-xs text-muted pt-2 border-t border-line">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button type="button" onClick={() => setMode("register")} className="text-gold">
                  Create one
                </button>
              </>
            ) : (
              <>
                Have an account?{" "}
                <button type="button" onClick={() => setMode("login")} className="text-gold">
                  Log in
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
