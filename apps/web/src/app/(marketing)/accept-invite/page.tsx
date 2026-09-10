"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthCard, FieldLabel, darkInputStyle, primaryButtonStyle } from "@/components/AuthCard";
import { api, ApiError, MEMBER_ROLES, type Me, type PublicInvitation } from "@/lib/api";

function roleLabel(code: string): string {
  return MEMBER_ROLES.find((r) => r.value === code)?.label ?? code;
}

function AcceptInviteForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [invitation, setInvitation] = useState<PublicInvitation | null>(null);
  const [currentUser, setCurrentUser] = useState<Me | null | "unknown">("unknown");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      if (!token) {
        setLoadError("This invite link is missing its token.");
        return;
      }
      try {
        setInvitation(await api.getInvitation(token));
      } catch (err) {
        setLoadError(
          err instanceof ApiError && err.status === 410
            ? "This invitation is no longer valid — it may have expired, been revoked, or already been accepted."
            : "We couldn't find that invitation.",
        );
      }
      try {
        setCurrentUser(await api.me());
      } catch {
        setCurrentUser(null);
      }
    })();
  }, [token]);

  async function onAccept(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.acceptInvitation(token, invitation?.account_exists ? {} : { name, password });
      router.push("/home");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <AuthCard>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, marginBottom: 12 }}>Invite link not valid</h1>
        <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>{loadError}</p>
        <a href="/sign-in" style={{ color: "var(--color-primary)", fontSize: 14 }}>
          Go to sign in
        </a>
      </AuthCard>
    );
  }

  if (!invitation || currentUser === "unknown") {
    return (
      <AuthCard>
        <p style={{ color: "var(--text-on-dark-muted)" }}>Loading…</p>
      </AuthCard>
    );
  }

  const signedInAsInvitee = currentUser !== null && currentUser.email === invitation.email;
  const signedInAsSomeoneElse = currentUser !== null && currentUser.email !== invitation.email;

  return (
    <AuthCard>
      <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, marginBottom: 6 }}>You&rsquo;re invited</h1>
      <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 24 }}>
        Join <strong>{invitation.organisation_name}</strong> on DataLume as {roleLabel(invitation.role_code)}.
      </p>

      {signedInAsSomeoneElse && (
        <p style={{ color: "var(--color-warning)", fontSize: 13, marginBottom: 16 }}>
          You&rsquo;re signed in as {currentUser.email}. Sign out first to accept this invitation for{" "}
          {invitation.email}.
        </p>
      )}

      {invitation.account_exists && !signedInAsInvitee && !signedInAsSomeoneElse && (
        <>
          <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 16 }}>
            An account already exists for {invitation.email}. Sign in, then open this link again to accept.
          </p>
          <a href="/sign-in" style={{ ...primaryButtonStyle, display: "block", textAlign: "center", textDecoration: "none" }}>
            Go to sign in
          </a>
        </>
      )}

      {invitation.account_exists && signedInAsInvitee && (
        <form onSubmit={onAccept}>
          <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 16 }}>
            Signed in as {currentUser.email} — accept to join.
          </p>
          {submitError && <p style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 16 }}>{submitError}</p>}
          <button type="submit" style={primaryButtonStyle} disabled={submitting}>
            {submitting ? "Joining…" : `Accept and join ${invitation.organisation_name}`}
          </button>
        </form>
      )}

      {!invitation.account_exists && !signedInAsSomeoneElse && (
        <form onSubmit={onAccept}>
          <FieldLabel htmlFor="accept-name">Your name</FieldLabel>
          <input id="accept-name" style={darkInputStyle} required value={name} onChange={(e) => setName(e.target.value)} />

          <FieldLabel htmlFor="accept-email">Email</FieldLabel>
          <input id="accept-email" style={darkInputStyle} value={invitation.email} disabled />

          <FieldLabel htmlFor="accept-password">Choose a password</FieldLabel>
          <input
            id="accept-password"
            style={darkInputStyle}
            type="password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {submitError && <p style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 16 }}>{submitError}</p>}
          <button type="submit" style={primaryButtonStyle} disabled={submitting}>
            {submitting ? "Joining…" : `Join ${invitation.organisation_name}`}
          </button>
        </form>
      )}
    </AuthCard>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<AuthCard><p style={{ color: "var(--text-on-dark-muted)" }}>Loading…</p></AuthCard>}>
      <AcceptInviteForm />
    </Suspense>
  );
}
