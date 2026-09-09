export function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div
        style={{
          background: "#12182b",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 16,
          padding: 40,
          width: "100%",
          maxWidth: 420,
        }}
      >
        {children}
      </div>
    </div>
  );
}

export function AuthTabs({ active }: { active: "sign-in" | "sign-up" }) {
  const tab = (href: string, key: "sign-in" | "sign-up", label: string) => (
    <a
      href={href}
      style={{
        flex: 1,
        textAlign: "center",
        padding: "10px 0",
        fontWeight: 600,
        fontSize: 14,
        color: active === key ? "var(--text-on-dark)" : "var(--text-on-dark-muted)",
        borderBottom: active === key ? "2px solid var(--color-primary)" : "2px solid transparent",
        textDecoration: "none",
      }}
    >
      {label}
    </a>
  );
  return (
    <div style={{ display: "flex", marginBottom: 24, borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
      {tab("/sign-in", "sign-in", "Sign In")}
      {tab("/sign-up", "sign-up", "Create Account")}
    </div>
  );
}

// htmlFor is required, not optional: this label and its input are
// separate siblings at every call site (not a nested <label><input/>
// pair), so without htmlFor matching the input's id, the label and
// input have zero programmatic association — a screen reader
// announces the input with no accessible name at all. Caught during
// Sprint 24's accessibility pass (architecture/09's hardening line).
export function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} style={{ display: "block", fontSize: 13, color: "var(--text-on-dark-muted)", marginBottom: 6 }}>
      {children}
    </label>
  );
}

export const darkInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.03)",
  color: "var(--text-on-dark)",
  fontSize: 14,
  marginBottom: 16,
};

export const primaryButtonStyle: React.CSSProperties = {
  width: "100%",
  padding: "12px 0",
  borderRadius: 8,
  border: "none",
  background: "var(--color-primary)",
  color: "#fff",
  fontWeight: 600,
  fontSize: 14,
  cursor: "pointer",
};
