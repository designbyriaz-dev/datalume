import { ComponentDetailClient } from "./ComponentDetailClient";

// Next.js 16 async params — see apps/web/src/app/(app)/properties/[id]/page.tsx
// for the same pattern with more detail in the comment.
export default async function ComponentDetailPage(props: PageProps<"/components/[id]">) {
  const { id } = await props.params;
  return <ComponentDetailClient componentId={id} />;
}
