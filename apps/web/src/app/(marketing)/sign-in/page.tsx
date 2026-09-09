"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthCard, AuthTabs, FieldLabel, darkInputStyle, primaryButtonStyle } from "@/components/AuthCard";
import { api, ApiError } from "@/lib/api";

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login({ email, password });
      router.push("/home");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Welcome to DataLume</h1>
      <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginTop: 6, marginBottom: 24 }}>
        Sign in to your organisation&rsquo;s workspace.
      </p>
      <AuthTabs active="sign-in" />
      <form onSubmit={onSubmit}>
        <FieldLabel htmlFor="sign-in-email">Email</FieldLabel>
        <input
          id="sign-in-email"
          style={darkInputStyle}
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@organisation.com"
        />
        <FieldLabel htmlFor="sign-in-password">Password</FieldLabel>
        <input
          id="sign-in-password"
          style={darkInputStyle}
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••••"
        />
        {error && (
          <p style={{ color: "var(--color-critical)", fontSize: 13, marginTop: -8, marginBottom: 16 }}>{error}</p>
        )}
        <button type="submit" style={primaryButtonStyle} disabled={submitting}>
          {submitting ? "Signing in…" : "Sign In"}
        </button>
      </form>
      <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginTop: 20, textAlign: "center" }}>
        Don&rsquo;t have an account?{" "}
        <a href="/sign-up" style={{ color: "var(--color-primary)" }}>
          Create one
        </a>
      </p>
    </AuthCard>
  );
}
