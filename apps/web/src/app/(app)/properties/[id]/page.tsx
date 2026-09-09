import { PropertyDetailClient } from "./PropertyDetailClient";

// Next.js 16: dynamic route params are async — see
// node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md
// "Async Request APIs". This stays a thin server wrapper so the actual
// page can be a client component (it needs hooks for data fetching).
export default async function PropertyDetailPage(props: PageProps<"/properties/[id]">) {
  const { id } = await props.params;
  return <PropertyDetailClient propertyId={id} />;
}
