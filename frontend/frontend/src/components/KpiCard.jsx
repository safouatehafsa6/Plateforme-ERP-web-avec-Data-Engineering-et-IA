export default function KpiCard({ label, valeur, variation, positif = true }) {
  return (
    <div className="kpi-carte">
      <div className="kpi-carte__label">{label}</div>
      <div className="kpi-carte__valeur">{valeur}</div>
      {variation && (
        <div className={`kpi-carte__variation ${positif ? "kpi-carte__variation--hausse" : "kpi-carte__variation--baisse"}`}>
          {positif ? "↑" : "↓"} {variation}
        </div>
      )}
    </div>
  );
}
