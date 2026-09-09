"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type PropertyOut, type StockConditionSurveyOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

export default function StockConditionPage() {
  const [surveys, setSurveys] = useState<StockConditionSurveyOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [propertyId, setPropertyId] = useState("");
  const [surveyor, setSurveyor] = useState("");
  const [ratingElement, setRatingElement] = useState("");
  const [ratingValue, setRatingValue] = useState("");
  const [nextSurveyDue, setNextSurveyDue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    setSurveys(await api.listStockConditionSurveys(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [surveyList, propertyList] = await Promise.all([api.listStockConditionSurveys(id), api.listProperties(id)]);
        setSurveys(surveyList);
        setProperties(propertyList);
        if (propertyList[0]) setPropertyId(propertyList[0].id);
      } catch {
        setLoadError("Couldn't load stock condition surveys.");
      }
    })();
  }, []);

  async function onAddSurvey() {
    const id = orgId();
    if (!id || !propertyId || !surveyor.trim()) {
      setFormError("Pick a property and a surveyor.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const condition_ratings = ratingElement.trim() ? { [ratingElement.trim()]: ratingValue.trim() || "UNRATED" } : {};
      await api.createStockConditionSurvey(id, {
        property_id: propertyId,
        survey_date: new Date().toISOString().slice(0, 10),
        surveyor: surveyor.trim(),
        condition_ratings,
        next_survey_due: nextSurveyDue || undefined,
      });
      setSurveyor("");
      setRatingElement("");
      setRatingValue("");
      setNextSurveyDue("");
      await refresh();
    } catch {
      setFormError("Couldn't record that survey.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!surveys || !properties) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const propertyAddress = (id: string) => properties.find((p) => p.id === id)?.address ?? id.slice(0, 8);

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Stock Condition</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Periodic per-property surveys — condition ratings are a free-form element → rating map, not a fixed
        methodology this build assumes. Missing or overdue surveys show up on Data Health; they feed Planned
        Investment as one more input signal, not a separate scoring system.
      </p>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Record a survey</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1.5fr 1fr 1fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Property</label>
            <select style={inputStyle} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Surveyor</label>
            <input style={inputStyle} value={surveyor} onChange={(e) => setSurveyor(e.target.value)} placeholder="e.g. Surveyor Ltd" />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Element</label>
            <input style={inputStyle} value={ratingElement} onChange={(e) => setRatingElement(e.target.value)} placeholder="e.g. roof" />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Rating</label>
            <input style={inputStyle} value={ratingValue} onChange={(e) => setRatingValue(e.target.value)} placeholder="e.g. GOOD" />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Next due</label>
            <input style={inputStyle} type="date" value={nextSurveyDue} onChange={(e) => setNextSurveyDue(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddSurvey} disabled={submitting}>
            {submitting ? "Recording…" : "Record"}
          </button>
        </div>
        {properties.length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>Add a property first before recording a survey.</div>
        )}
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Surveys</h2>
      {surveys.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No surveys recorded yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {surveys.map((s) => (
            <li key={s.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>
                  <Link href={`/properties/${s.property_id}`} style={{ color: "var(--color-primary)" }}>
                    {propertyAddress(s.property_id)}
                  </Link>
                  {" · "}
                  {s.survey_date} by {s.surveyor}
                </span>
                {s.next_survey_due && <span style={{ color: "var(--text-secondary)" }}>Next due {s.next_survey_due}</span>}
              </div>
              {Object.keys(s.condition_ratings).length > 0 && (
                <div style={{ color: "var(--text-secondary)", marginTop: 4 }}>
                  {Object.entries(s.condition_ratings)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
