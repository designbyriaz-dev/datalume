"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError, MEMBER_ROLES, type Invitation, type Member } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const cardStyle: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-card)",
  padding: 24,
  marginBottom: 24,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  fontSize: 12,
  color: "var(--text-secondary)",
  fontWeight: 600,
  padding: "0 12px 8px 0",
  borderBottom: "1px solid var(--border-subtle)",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px 10px 0",
  fontSize: 14,
  borderBottom: "1px solid var(--border-subtle)",
};

function roleLabel(code: string): string {
  return MEMBER_ROLES.find((r) => r.value === code)?.label ?? code;
}

export default function UsersPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [roleCode, setRoleCode] = useState("VIEWER");
  const [inviting, setInviting] = useState(false);
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const orgId = typeof window !== "undefined" ? window.localStorage.getItem(SELECTED_ORG_KEY) : null;

  async function refresh() {
    if (!orgId) return;
    try {
      const [memberList, invitationList] = await Promise.all([api.listMembers(orgId), api.listInvitations(orgId)]);
      setMembers(memberList);
      setInvitations(invitationList);
      setForbidden(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError("Couldn't load organisation members.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      await refresh();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setInviting(true);
    setError(null);
    setLastInviteUrl(null);
    try {
      const invitation = await api.inviteMember(orgId, email, roleCode);
      setLastInviteUrl(invitation.invite_url);
      setEmail("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong sending the invitation.");
    } finally {
      setInviting(false);
    }
  }

  async function onRevoke(invitationId: string) {
    if (!orgId) return;
    try {
      await api.revokeInvitation(orgId, invitationId);
      await refresh();
    } catch {
      setError("Couldn't revoke that invitation.");
    }
  }

  async function onCopy(invitationId: string, url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(invitationId);
      setTimeout(() => setCopiedId((id) => (id === invitationId ? null : id)), 1500);
    } catch {
      // Clipboard access can be denied by the browser — the link is
      // still visible on screen to select/copy manually.
    }
  }

  if (!orgId) {
    return <div style={{ color: "var(--text-secondary)" }}>No organisation selected.</div>;
  }
  if (loading) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 880 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Users</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Who has access to your DataLume workspace, and what they can do.
      </p>

      {forbidden ? (
        <div style={cardStyle}>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            Only an Owner or Admin can manage members. Ask one of your organisation&rsquo;s Owners to make
            changes here.
          </p>
        </div>
      ) : (
        <>
          <div style={cardStyle}>
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, marginBottom: 16 }}>Invite a teammate</h2>
            <form onSubmit={onInvite} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 220px" }}>
                <label htmlFor="invite-email" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Work email
                </label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--border-subtle)" }}
                />
              </div>
              <div style={{ flex: "1 1 180px" }}>
                <label htmlFor="invite-role" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Role
                </label>
                <select
                  id="invite-role"
                  value={roleCode}
                  onChange={(e) => setRoleCode(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--border-subtle)" }}
                >
                  {MEMBER_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={inviting}
                style={{
                  padding: "9px 18px",
                  borderRadius: 8,
                  border: "none",
                  background: "var(--color-primary)",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: inviting ? "default" : "pointer",
                }}
              >
                {inviting ? "Sending…" : "Send invite"}
              </button>
            </form>

            {error && (
              <p style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 12, marginBottom: 0 }}>{error}</p>
            )}

            {lastInviteUrl && (
              <div
                style={{
                  marginTop: 16,
                  background: "var(--bg-app)",
                  borderRadius: 8,
                  padding: "12px 14px",
                  fontSize: 13,
                }}
              >
                There&rsquo;s no email sending configured in this environment — copy this link and send it to
                them yourself:
                <div style={{ marginTop: 6, wordBreak: "break-all", fontFamily: "monospace" }}>{lastInviteUrl}</div>
              </div>
            )}
          </div>

          {invitations && invitations.length > 0 && (
            <div style={cardStyle}>
              <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, marginBottom: 16 }}>Pending invitations</h2>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Email</th>
                    <th style={thStyle}>Role</th>
                    <th style={thStyle}>Expires</th>
                    <th style={thStyle}></th>
                  </tr>
                </thead>
                <tbody>
                  {invitations.map((inv) => (
                    <tr key={inv.id}>
                      <td style={tdStyle}>{inv.email}</td>
                      <td style={tdStyle}>{roleLabel(inv.role_code)}</td>
                      <td style={tdStyle}>{new Date(inv.expires_at).toLocaleDateString()}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        <button
                          onClick={() => onCopy(inv.id, inv.invite_url)}
                          style={{ border: "none", background: "none", color: "var(--color-primary)", fontSize: 13, cursor: "pointer", marginRight: 12 }}
                        >
                          {copiedId === inv.id ? "Copied" : "Copy link"}
                        </button>
                        <button
                          onClick={() => onRevoke(inv.id)}
                          style={{ border: "none", background: "none", color: "var(--color-critical)", fontSize: 13, cursor: "pointer" }}
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={cardStyle}>
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, marginBottom: 16 }}>Members</h2>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Email</th>
                  <th style={thStyle}>Role</th>
                  <th style={thStyle}>Status</th>
                </tr>
              </thead>
              <tbody>
                {members?.map((m) => (
                  <tr key={m.user_id}>
                    <td style={tdStyle}>{m.name}</td>
                    <td style={tdStyle}>{m.email}</td>
                    <td style={tdStyle}>{roleLabel(m.role_code)}</td>
                    <td style={tdStyle}>
                      <StatusBadge label={m.status} variant={m.status === "ACTIVE" ? "success" : "neutral"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
