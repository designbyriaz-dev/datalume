import { DevelopmentDetailClient } from "./DevelopmentDetailClient";

// Next.js 16 async params — see apps/web/src/app/(app)/properties/[id]/page.tsx
// for the same pattern with more detail in the comment.
export default async function DevelopmentDetailPage(props: PageProps<"/developments/[id]">) {
  const { id } = await props.params;
  return <DevelopmentDetailClient developmentId={id} />;
}
