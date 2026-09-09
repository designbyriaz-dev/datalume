export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--bg-dark)", minHeight: "100vh", color: "var(--text-on-dark)" }}>
      {children}
    </div>
  );
}
