"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthCard, AuthTabs, FieldLabel, darkInputStyle, primaryButtonStyle } from "@/components/AuthCard";
import { api, ApiError, ORGANISATION_TYPES } from "@/lib/api";

export default function SignUpPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organisationName, setOrganisationName] = useState("");
  const [organisationType, setOrganisationType] = useState<string>(ORGANISATION_TYPES[0].value);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.signup({
        name,
        email,
        password,
        organisation_name: organisationName,
        organisation_type: organisationType,
        goals: [],
      });
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
        Create your organisation&rsquo;s workspace. No credit card required.
      </p>
      <AuthTabs active="sign-up" />
      <form onSubmit={onSubmit}>
        <FieldLabel htmlFor="sign-up-name">Your name</FieldLabel>
        <input id="sign-up-name" style={darkInputStyle} required value={name} onChange={(e) => setName(e.target.value)} />

        <FieldLabel htmlFor="sign-up-email">Work email</FieldLabel>
        <input
          id="sign-up-email"
          style={darkInputStyle}
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <FieldLabel htmlFor="sign-up-password">Password</FieldLabel>
        <input
          id="sign-up-password"
          style={darkInputStyle}
          type="password"
          required
          minLength={10}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <FieldLabel htmlFor="sign-up-org-name">Organisation name</FieldLabel>
        <input
          id="sign-up-org-name"
          style={darkInputStyle}
          required
          value={organisationName}
          onChange={(e) => setOrganisationName(e.target.value)}
        />

        <FieldLabel htmlFor="sign-up-org-type">What type of organisation are you?</FieldLabel>
        <select
          id="sign-up-org-type"
          style={darkInputStyle}
          value={organisationType}
          onChange={(e) => setOrganisationType(e.target.value)}
        >
          {ORGANISATION_TYPES.map((t) => (
            <option key={t.value} value={t.value} style={{ color: "#000" }}>
              {t.label}
            </option>
          ))}
        </select>

        {error && (
          <p style={{ color: "var(--color-critical)", fontSize: 13, marginTop: -8, marginBottom: 16 }}>{error}</p>
        )}
        <button type="submit" style={primaryButtonStyle} disabled={submitting}>
          {submitting ? "Creating your workspace…" : "Start your free trial"}
        </button>
      </form>
      <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginTop: 20, textAlign: "center" }}>
        Already have an account?{" "}
        <a href="/sign-in" style={{ color: "var(--color-primary)" }}>
          Sign in
        </a>
      </p>
    </AuthCard>
  );
}
