/** Shared inline style constants for simple admin forms/tables across the
 * app shell — factored out once enough pages needed the same three
 * declarations (properties, developments, buildings all do). */

export const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid var(--border-subtle)",
  fontSize: 13,
};

export const primaryBtn: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "none",
  background: "var(--color-primary)",
  color: "#fff",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};

export const secondaryBtn: React.CSSProperties = {
  ...primaryBtn,
  background: "var(--bg-app)",
  color: "var(--text-primary)",
  border: "1px solid var(--border-subtle)",
};
