"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { api, ApiError, type Me, type Membership, type WorkspaceLayout } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [layout, setLayout] = useState<WorkspaceLayout | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meResponse = await api.me();
        if (cancelled) return;
        const firstMembership = meResponse.memberships[0];
        if (!firstMembership) {
          setError("Your account has no organisation memberships yet.");
          return;
        }
        const storedOrgId =
          typeof window !== "undefined" ? window.localStorage.getItem(SELECTED_ORG_KEY) : null;
        const selected =
          meResponse.memberships.find((m) => m.organisation_id === storedOrgId) ?? firstMembership;
        window.localStorage.setItem(SELECTED_ORG_KEY, selected.organisation_id);

        const workspaceLayout = await api.workspaceLayout(selected.organisation_id);
        if (cancelled) return;
        setMe(meResponse);
        setMembership(selected);
        setLayout(workspaceLayout);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/sign-in");
          return;
        }
        setError("Couldn't reach the DataLume API. Is it running?");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (error) {
    return (
      <div style={{ padding: 48, textAlign: "center", color: "var(--text-secondary)" }}>{error}</div>
    );
  }

  if (!me || !membership || !layout) {
    return <div style={{ padding: 48, textAlign: "center", color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ display: "flex" }}>
      <Sidebar
        navSections={layout.nav_sections}
        organisationName={membership.organisation_name}
        propertyCount={0}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <TopBar userName={me.name} roleCode={membership.role_code} />
        <main style={{ padding: 24 }}>{children}</main>
      </div>
    </div>
  );
}
