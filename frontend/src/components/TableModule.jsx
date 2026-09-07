export default function TableModule({ colonnes, lignes }) {
  return (
    <div className="table-module">
      <table>
        <thead>
          <tr>
            {colonnes.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((ligne, i) => (
            <tr key={i}>
              {ligne.map((valeur, j) => (
                <td key={j}>{valeur}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
