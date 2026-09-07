// Motif abstrait de nœuds reliés — évoque les modules interconnectés
// de la plateforme (ERP, Data, IA) sans être une illustration littérale.
export default function ReseauDecoratif() {
  const noeuds = [
    [40, 60], [160, 30], [280, 90], [90, 160],
    [220, 190], [320, 140], [60, 260], [200, 300],
  ];
  const liens = [
    [0, 1], [1, 2], [0, 3], [1, 4], [2, 5],
    [3, 4], [4, 5], [3, 6], [4, 7], [6, 7],
  ];

  return (
    <svg
      className="connexion-marque__reseau"
      viewBox="0 0 360 360"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {liens.map(([a, b], i) => (
        <line
          key={i}
          x1={noeuds[a][0]}
          y1={noeuds[a][1]}
          x2={noeuds[b][0]}
          y2={noeuds[b][1]}
          stroke="#9fb3bd"
          strokeWidth="1"
          opacity="0.5"
        />
      ))}
      {noeuds.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 4 : 2.5} fill="#c68a3d" opacity="0.85" />
      ))}
    </svg>
  );
}
