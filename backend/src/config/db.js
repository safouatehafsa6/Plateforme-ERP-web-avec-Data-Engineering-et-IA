import pg from "pg";
import "dotenv/config";

const { Pool } = pg;

// Connexion permanente à la base centrale (toujours active).
export const poolCentral = new Pool({
  host: process.env.DB_HOST || "localhost",
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || "erp_user",
  password: process.env.DB_PASSWORD || "erp_password",
  database: process.env.DB_CENTRAL_NAME || "erp_db",
});

// Cache des connexions aux bases entreprise, pour ne pas recréer un pool
// à chaque requête (une base = un nom = un pool réutilisé).
const poolsEntreprise = new Map();

export function getPoolEntreprise(nomBase) {
  if (poolsEntreprise.has(nomBase)) {
    return poolsEntreprise.get(nomBase);
  }

  const pool = new Pool({
    host: process.env.DB_HOST || "localhost",
    port: process.env.DB_PORT || 5432,
    user: process.env.DB_USER || "erp_user",
    password: process.env.DB_PASSWORD || "erp_password",
    database: nomBase,
  });

  poolsEntreprise.set(nomBase, pool);
  return pool;
}
