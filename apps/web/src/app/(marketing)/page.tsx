import Link from "next/link";

const FEATURES = [
  { title: "Upload", body: "Bring in spreadsheets, exports and manual records from every system you already use." },
  { title: "Understand", body: "DataLume validates, maps and cleans it into one connected property model." },
  { title: "Act", body: "See what needs attention, ask questions, and generate the reports your board needs." },
];

export default function LandingPage() {
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "80px 24px" }}>
      <nav style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 96 }}>
        <div style={{ fontWeight: 700, fontSize: 20 }}>
          DataLume
          <div style={{ fontSize: 10, letterSpacing: 2, color: "var(--text-on-dark-muted)", fontWeight: 500 }}>
            PROPERTY INTELLIGENCE
          </div>
        </div>
        <Link
          href="/sign-in"
          style={{ color: "var(--text-on-dark)", fontSize: 14, textDecoration: "none" }}
        >
          Already have an account? Sign in
        </Link>
      </nav>

      <h1 style={{ fontSize: 48, fontWeight: 700, lineHeight: 1.15, maxWidth: 640, margin: 0 }}>
        Turn your property data into brighter decisions.
      </h1>
      <p style={{ color: "var(--text-on-dark-muted)", fontSize: 18, maxWidth: 560, marginTop: 20 }}>
        One property. One view. Every signal. DataLume connects development, repairs,
        compliance and commercial data into one explainable picture — ask your portfolio
        anything.
      </p>

      <div style={{ display: "flex", gap: 16, marginTop: 40 }}>
        <Link
          href="/sign-up"
          style={{
            background: "var(--color-primary)",
            color: "#fff",
            padding: "12px 24px",
            borderRadius: 8,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          Start your free trial →
        </Link>
        <span
          style={{
            border: "1px solid rgba(255,255,255,0.2)",
            padding: "12px 24px",
            borderRadius: 8,
            fontWeight: 600,
          }}
        >
          Book a demo
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24, marginTop: 64 }}>
        {FEATURES.map((f) => (
          <div key={f.title} style={{ background: "rgba(255,255,255,0.04)", borderRadius: 12, padding: 20 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{f.title}</div>
            <div style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>{f.body}</div>
          </div>
        ))}
      </div>

      <footer
        style={{
          marginTop: 96,
          paddingTop: 24,
          borderTop: "1px solid rgba(255,255,255,0.1)",
          color: "var(--text-on-dark-muted)",
          fontSize: 13,
        }}
      >
        ONE PROPERTY. ONE VIEW. EVERY SIGNAL.
      </footer>
    </main>
  );
}
