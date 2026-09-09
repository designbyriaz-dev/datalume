/** Design system §4 "KPI stat cards" — architecture/08-frontend-design.md §3.
 * icon in a tinted rounded square, large bold value, label, optional trend delta. */

export function KpiStatCard({
  label,
  value,
  tint = "var(--color-primary)",
}: {
  label: string;
  value: string;
  tint?: string;
}) {
  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: 20,
        flex: 1,
        minWidth: 160,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: `color-mix(in srgb, ${tint} 15%, transparent)`,
          marginBottom: 12,
        }}
      />
      <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary)" }}>{value}</div>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>{label}</div>
    </div>
  );
}
