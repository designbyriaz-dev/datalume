/** The only sanctioned way to render a status/priority indicator — pairs
 * colour with an icon and text label, never colour alone.
 * See architecture/08-frontend-design.md §4 (accessibility). */

const VARIANTS = {
  success: { bg: "#d1fae5", fg: "#047857", icon: "✓" },
  warning: { bg: "#fef3c7", fg: "#b45309", icon: "!" },
  critical: { bg: "#fee2e2", fg: "#b91c1c", icon: "✕" },
  neutral: { bg: "#f1f5f9", fg: "#475569", icon: "•" },
} as const;

export function StatusBadge({
  label,
  variant,
}: {
  label: string;
  variant: keyof typeof VARIANTS;
}) {
  const v = VARIANTS[variant];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        background: v.bg,
        color: v.fg,
        borderRadius: 999,
        padding: "2px 10px",
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      <span aria-hidden>{v.icon}</span>
      {label}
    </span>
  );
}
