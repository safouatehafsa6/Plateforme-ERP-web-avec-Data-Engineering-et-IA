import bcrypt from "bcrypt";
import "dotenv/config";
import { poolCentral } from "../config/db.js";

async function seed() {
  const email = "admin@benjeddou-erp.ma";
  const motDePasse = "Test1234!";
  const hash = await bcrypt.hash(motDePasse, 10);

  await poolCentral.query(
    `INSERT INTO super_admin (nom, email, mot_de_passe)
     VALUES ($1, $2, $3)
     ON CONFLICT (email) DO UPDATE SET mot_de_passe = EXCLUDED.mot_de_passe`,
    ["Admin Test", email, hash]
  );

  console.log("Compte de test créé :");
  console.log("  email :", email);
  console.log("  mot de passe :", motDePasse);
  process.exit(0);
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
