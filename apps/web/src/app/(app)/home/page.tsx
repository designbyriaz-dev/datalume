import { EmptyState } from "@/components/EmptyState";

export default function HomePage() {
  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Good morning 👋</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: 4, marginBottom: 24 }}>
        Here&rsquo;s what&rsquo;s happening across your portfolio.
      </p>

      <EmptyState
        title="No property data yet"
        body="Once you upload a dataset or add records manually, your Home dashboard will show KPIs, compliance status, repairs, and DataLume Intelligence insights here — all traceable back to the records behind them."
        actionLabel="Add Data"
        actionHref="/data-and-uploads"
      />
    </div>
  );
}
