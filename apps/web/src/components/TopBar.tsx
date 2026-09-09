"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function TopBar({ userName, roleCode }: { userName: string; roleCode: string }) {
  const router = useRouter();

  async function onSignOut() {
    await api.logout();
    router.push("/sign-in");
  }

  const initials = userName
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 24px",
        borderBottom: "1px solid var(--border-subtle)",
        background: "var(--bg-card)",
      }}
    >
      <div
        style={{
          flex: 1,
          maxWidth: 420,
          background: "var(--bg-app)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          padding: "8px 12px",
          fontSize: 13,
          color: "var(--text-secondary)",
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>Search properties, repairs, compliance…</span>
        <span
          style={{
            border: "1px solid var(--border-subtle)",
            borderRadius: 4,
            padding: "0 6px",
            fontSize: 11,
          }}
        >
          ⌘K
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <button
          onClick={onSignOut}
          style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            background: "none",
            border: "none",
            cursor: "pointer",
          }}
        >
          Sign out
        </button>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            background: "var(--color-purple-accent)",
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            fontWeight: 600,
          }}
          title={`${userName} — ${roleCode}`}
        >
          {initials}
        </div>
      </div>
    </header>
  );
}
