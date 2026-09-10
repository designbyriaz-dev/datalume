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

  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await api.login({ email, password });
      if (result.mfa_required) {
        setMfaToken(result.mfa_token);
      } else {
        router.push("/home");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onChallenge(e: React.FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await api.mfaChallenge(mfaToken, code);
      router.push("/home");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (mfaToken) {
    return (
      <AuthCard>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Enter your code</h1>
        <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginTop: 6, marginBottom: 24 }}>
          Open your authenticator app and enter the 6-digit code for DataLume.
        </p>
        <form onSubmit={onChallenge}>
          <FieldLabel htmlFor="sign-in-mfa-code">Authentication code</FieldLabel>
          <input
            id="sign-in-mfa-code"
            style={darkInputStyle}
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="123456"
          />
          {error && (
            <p style={{ color: "var(--color-critical)", fontSize: 13, marginTop: -8, marginBottom: 16 }}>{error}</p>
          )}
          <button type="submit" style={primaryButtonStyle} disabled={submitting}>
            {submitting ? "Verifying…" : "Verify"}
          </button>
        </form>
        <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginTop: 20, textAlign: "center" }}>
          <button
            type="button"
            onClick={() => {
              setMfaToken(null);
              setCode("");
              setError(null);
            }}
            style={{ background: "none", border: "none", color: "var(--color-primary)", cursor: "pointer", fontSize: 13 }}
          >
            Back to sign in
          </button>
        </p>
      </AuthCard>
    );
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
