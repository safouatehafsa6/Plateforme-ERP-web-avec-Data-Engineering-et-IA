// Arrière-plan animé des pages publiques : halos flottants, grille, réseau
// de nœuds qui pulsent et petites particules. Purement décoratif.
const NOEUDS = [
  [8, 18], [24, 8], [42, 22], [60, 10], [78, 24], [92, 12],
  [14, 52], [34, 64], [54, 48], [74, 66], [90, 54], [22, 88], [48, 90], [82, 88],
];
const LIENS = [
  [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 6], [2, 8], [4, 10],
  [6, 7], [7, 8], [8, 9], [9, 10], [7, 11], [8, 12], [9, 13], [11, 12], [12, 13],
];

export default function FondAnime() {
  return (
    <div className="fond-anime" aria-hidden="true">
      <span className="fond-anime__blob fond-anime__blob--1" />
      <span className="fond-anime__blob fond-anime__blob--2" />
      <span className="fond-anime__blob fond-anime__blob--3" />
      <span className="fond-anime__grille" />
      <svg className="fond-anime__reseau" viewBox="0 0 100 100" preserveAspectRatio="none">
        {LIENS.map(([a, b], i) => (
          <line
            key={i}
            className="fond-anime__lien"
            style={{ animationDelay: `${(i % 6) * 0.7}s` }}
            x1={NOEUDS[a][0]} y1={NOEUDS[a][1]}
            x2={NOEUDS[b][0]} y2={NOEUDS[b][1]}
          />
        ))}
      </svg>
      {NOEUDS.map(([x, y], i) => (
        <span
          key={i}
          className="fond-anime__noeud"
          style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${(i % 7) * 0.5}s` }}
        />
      ))}
      {Array.from({ length: 12 }).map((_, i) => (
        <span
          key={i}
          className="fond-anime__particule"
          style={{
            left: `${(i * 83) % 100}%`,
            animationDuration: `${14 + (i % 5) * 4}s`,
            animationDelay: `${-(i * 2.3)}s`,
          }}
        />
      ))}
    </div>
  );
}
