export function EmptyState({
  title,
  body,
  actionLabel,
  actionHref,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px dashed var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: 48,
        textAlign: "center",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 6 }}>{title}</div>
      <div style={{ color: "var(--text-secondary)", fontSize: 14, maxWidth: 420, margin: "0 auto" }}>{body}</div>
      {actionLabel && actionHref && (
        <a
          href={actionHref}
          style={{
            display: "inline-block",
            marginTop: 20,
            background: "var(--color-primary)",
            color: "#fff",
            padding: "10px 20px",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          {actionLabel}
        </a>
      )}
    </div>
  );
}
