import { BuildingDetailClient } from "./BuildingDetailClient";

// Next.js 16 async params — see apps/web/src/app/(app)/properties/[id]/page.tsx
// for the same pattern with more detail in the comment.
export default async function BuildingDetailPage(props: PageProps<"/buildings/[id]">) {
  const { id } = await props.params;
  return <BuildingDetailClient buildingId={id} />;
}
