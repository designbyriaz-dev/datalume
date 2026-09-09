"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavSection } from "@/lib/api";

const SECONDARY_NAV = [
  { key: "organisation", label: "Organisation", href: "/organisation" },
  { key: "users", label: "Users", href: "/organisation/users" },
  { key: "billing", label: "Billing", href: "/organisation/billing" },
  { key: "settings", label: "Settings", href: "/settings" },
];

export function Sidebar({
  navSections,
  organisationName,
  propertyCount,
}: {
  navSections: NavSection[];
  organisationName: string;
  propertyCount: number;
}) {
  const pathname = usePathname();

  return (
    <aside
      style={{
        width: 240,
        flexShrink: 0,
        background: "var(--bg-card)",
        borderRight: "1px solid var(--border-subtle)",
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        position: "sticky",
        top: 0,
      }}
    >
      <div style={{ padding: "20px 20px 12px" }}>
        <div style={{ fontWeight: 700, fontSize: 18, color: "var(--text-primary)" }}>DataLume</div>
        <div style={{ fontSize: 9, letterSpacing: 1.5, color: "var(--text-secondary)", fontWeight: 600 }}>
          PROPERTY INTELLIGENCE
        </div>
      </div>

      <nav style={{ flex: 1, padding: "8px 12px", overflowY: "auto" }}>
        {navSections.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.key}
              href={item.href}
              style={{
                display: "block",
                padding: "9px 12px",
                borderRadius: 8,
                marginBottom: 2,
                fontSize: 14,
                fontWeight: 500,
                textDecoration: "none",
                color: active ? "#fff" : "var(--text-primary)",
                background: active ? "var(--color-primary)" : "transparent",
              }}
            >
              {item.label}
            </Link>
          );
        })}

        <div style={{ height: 1, background: "var(--border-subtle)", margin: "12px 4px" }} />

        {SECONDARY_NAV.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            style={{
              display: "block",
              padding: "9px 12px",
              borderRadius: 8,
              fontSize: 14,
              color: "var(--text-secondary)",
              textDecoration: "none",
            }}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div style={{ padding: 16, borderTop: "1px solid var(--border-subtle)" }}>
        <div
          style={{
            background: "var(--bg-app)",
            borderRadius: "var(--radius-card)",
            padding: 12,
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          Need help?{" "}
          <a href="mailto:support@datalume.example" style={{ color: "var(--color-primary)" }}>
            Contact support
          </a>
        </div>
        <div style={{ fontSize: 13 }}>
          <div style={{ fontWeight: 600 }}>{organisationName}</div>
          <div style={{ color: "var(--text-secondary)" }}>
            {propertyCount.toLocaleString()} {propertyCount === 1 ? "property" : "properties"}
          </div>
        </div>
      </div>
    </aside>
  );
}
