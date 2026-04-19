import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { Eyebrow } from "@/components/atoms/Eyebrow";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { useCurrentUser, useLoginMutation } from "@/lib/hooks/useAuth";

interface LocationState {
  from?: string;
}

export function Login() {
  const t = useT();
  const login = useLoginMutation();
  const { data: user, isPending } = useCurrentUser();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-fg3">
        {t("common.loading")}…
      </div>
    );
  }

  if (user) {
    const state = (location.state as LocationState | null) ?? null;
    return <Navigate to={state?.from ?? "/"} replace />;
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ email, password });
      const state = (location.state as LocationState | null) ?? null;
      navigate(state?.from ?? "/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(t("auth.invalid"));
      } else {
        setError(t("common.error"));
      }
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-creative-pattern px-6">
      <GlassCard className="w-full max-w-md !p-10">
        <Eyebrow>AIpacken</Eyebrow>
        <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-fg1">
          {t("auth.loginTitle")}
        </h1>
        <p className="mt-1 text-sm text-fg2">{t("auth.loginSubtitle")}</p>
        <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit}>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {t("auth.email")}
            </span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
              className="w-full rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {t("auth.password")}
            </span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              className="w-full rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          {error ? (
            <p className="rounded border border-[color:var(--border)] bg-teal-50 px-3 py-2 text-xs font-semibold text-danger">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={login.isPending}>
            {t("auth.submit")}
          </Button>
        </form>
      </GlassCard>
    </div>
  );
}
