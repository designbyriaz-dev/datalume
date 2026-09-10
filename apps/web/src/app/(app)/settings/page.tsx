"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError, type Me } from "@/lib/api";

const cardStyle: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-card)",
  padding: 24,
  marginBottom: 24,
  maxWidth: 520,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid var(--border-subtle)",
  marginBottom: 12,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "9px 18px",
  borderRadius: 8,
  border: "none",
  background: "var(--color-primary)",
  color: "#fff",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "9px 18px",
  borderRadius: 8,
  border: "1px solid var(--border-subtle)",
  background: "var(--bg-app)",
  color: "var(--text-primary)",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};

type EnrollState = { secret: string; otpauth_url: string } | null;

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const [enrolling, setEnrolling] = useState<EnrollState>(null);
  const [code, setCode] = useState("");
  const [disabling, setDisabling] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setMe(await api.me());
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onStartEnroll() {
    setError(null);
    setBusy(true);
    try {
      setEnrolling(await api.mfaEnroll());
    } catch {
      setError("Couldn't start MFA enrolment. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.mfaVerify(code);
      setEnrolling(null);
      setCode("");
      setMe(await api.me());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onDisable(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.mfaDisable(password);
      setDisabling(false);
      setPassword("");
      setMe(await api.me());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (loading || !me) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Settings</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>Your account security.</p>

      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>Two-factor authentication</h2>
          <StatusBadge label={me.mfa_enabled ? "Enabled" : "Not enabled"} variant={me.mfa_enabled ? "success" : "neutral"} />
        </div>

        {error && <p style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 16 }}>{error}</p>}

        {!me.mfa_enabled && !enrolling && (
          <>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 16 }}>
              Add a second step at sign-in using an authenticator app (Google Authenticator, 1Password, Authy —
              any app that supports TOTP codes).
            </p>
            <button onClick={onStartEnroll} disabled={busy} style={primaryBtnStyle}>
              {busy ? "Starting…" : "Set up two-factor authentication"}
            </button>
          </>
        )}

        {enrolling && (
          <form onSubmit={onVerify}>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 8 }}>
              In your authenticator app, add a new account using this setup key:
            </p>
            <div
              style={{
                background: "var(--bg-app)",
                borderRadius: 8,
                padding: "10px 12px",
                fontFamily: "monospace",
                fontSize: 15,
                letterSpacing: 1,
                marginBottom: 16,
                wordBreak: "break-all",
              }}
            >
              {enrolling.secret}
            </div>
            <label htmlFor="mfa-verify-code" style={{ display: "block", fontSize: 13, color: "var(--text-secondary)", marginBottom: 6 }}>
              Then enter the 6-digit code it shows
            </label>
            <input
              id="mfa-verify-code"
              style={inputStyle}
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              required
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
            />
            <div style={{ display: "flex", gap: 12 }}>
              <button type="submit" disabled={busy} style={primaryBtnStyle}>
                {busy ? "Verifying…" : "Verify and enable"}
              </button>
              <button
                type="button"
                style={secondaryBtnStyle}
                onClick={() => {
                  setEnrolling(null);
                  setCode("");
                  setError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {me.mfa_enabled && !disabling && (
          <>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 16 }}>
              Two-factor authentication is protecting your account. You&rsquo;ll be asked for a code from your
              authenticator app each time you sign in.
            </p>
            <button onClick={() => setDisabling(true)} style={secondaryBtnStyle}>
              Turn off
            </button>
          </>
        )}

        {disabling && (
          <form onSubmit={onDisable}>
            <label htmlFor="mfa-disable-password" style={{ display: "block", fontSize: 13, color: "var(--text-secondary)", marginBottom: 6 }}>
              Confirm your password to turn off two-factor authentication
            </label>
            <input
              id="mfa-disable-password"
              style={inputStyle}
              type="password"
              required
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div style={{ display: "flex", gap: 12 }}>
              <button type="submit" disabled={busy} style={primaryBtnStyle}>
                {busy ? "Turning off…" : "Turn off"}
              </button>
              <button
                type="button"
                style={secondaryBtnStyle}
                onClick={() => {
                  setDisabling(false);
                  setPassword("");
                  setError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
