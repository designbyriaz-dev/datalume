import { EmptyState } from "@/components/EmptyState";

export function ComingSoon({ title, sprintNote }: { title: string; sprintNote: string }) {
  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 24 }}>{title}</h1>
      <EmptyState
        title="Not built yet"
        body={`This module is on the roadmap but hasn't been implemented yet. ${sprintNote} See architecture/10-roadmap-and-acceptance.md for the full sprint order.`}
      />
    </div>
  );
}
