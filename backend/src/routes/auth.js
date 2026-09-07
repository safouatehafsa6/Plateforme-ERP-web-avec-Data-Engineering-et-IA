import { Router } from "express";
import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import { poolCentral } from "../config/db.js";
import { genererCaptcha } from "../utils/genererCaptcha.js";
import {
  enregistrerCaptcha,
  verifierEtConsommerCaptcha,
  etatProtection,
  enregistrerEchec,
  reinitialiserTentatives,
} from "../utils/protectionConnexion.js";
import { verifierRecaptcha } from "../utils/verifierRecaptcha.js";

const router = Router();

// GET /api/auth/captcha — génère un nouveau captcha local.
// Appelé au chargement de la page ET après chaque tentative échouée
// (le captcha est à usage unique, conformément à la demande de
// renouvellement automatique).
router.get("/captcha", (req, res) => {
  const { id, code, svg } = genererCaptcha();
  enregistrerCaptcha(id, code);
  if (process.env.NODE_ENV !== "production") {
    console.log(`[DEV] Captcha ${id} -> code: ${code}`);
  }
  res.json({ captchaId: id, svg });
});

// POST /api/auth/login
router.post("/login", async (req, res) => {
  const { email, motDePasse, captchaId, captchaValeur, recaptchaToken } = req.body;

  if (!email || !motDePasse) {
    return res.status(400).json({ message: "Email et mot de passe requis." });
  }

  const emailNormalise = email.toLowerCase().trim();
  const { protectionActive, echecs } = etatProtection(emailNormalise);

  // --- Couche 1 : au-delà de 2 échecs, le captcha local devient obligatoire ---
  if (protectionActive) {
    if (!captchaId || !captchaValeur) {
      return res.status(400).json({
        message: "Vérification de sécurité requise.",
        requiresCaptcha: true,
        requiresRecaptcha: echecs >= 4, // reCAPTCHA en renfort après 4 échecs
      });
    }

    const captchaValide = verifierEtConsommerCaptcha(captchaId, captchaValeur);
    if (!captchaValide) {
      enregistrerEchec(emailNormalise);
      return res.status(400).json({
        message: "Code de sécurité incorrect ou expiré.",
        requiresCaptcha: true,
        requiresRecaptcha: echecs >= 4,
      });
    }

    // --- Couche 2 : après 4 échecs, reCAPTCHA obligatoire en plus du captcha local ---
    if (echecs >= 4) {
      const recaptchaValide = await verifierRecaptcha(recaptchaToken);
      if (!recaptchaValide) {
        enregistrerEchec(emailNormalise);
        return res.status(400).json({
          message: "Vérification reCAPTCHA échouée.",
          requiresCaptcha: true,
          requiresRecaptcha: true,
        });
      }
    }
  }

  // --- Couche 3 : vérification réelle des identifiants ---
  // NOTE : pour cette démo de sécurité, la vérification se fait sur la
  // table super_admin de la base centrale. Le routage complet vers les
  // bases entreprise (utilisateur métier) est en cours d'implémentation
  // en parallèle (voir diagramme de séquence "Routage multi-tenant").
  try {
    const resultat = await poolCentral.query(
      "SELECT id, nom, email, mot_de_passe FROM super_admin WHERE email = $1",
      [emailNormalise]
    );

    const utilisateur = resultat.rows[0];
    const motDePasseValide = utilisateur
      ? await bcrypt.compare(motDePasse, utilisateur.mot_de_passe)
      : false;

    if (!utilisateur || !motDePasseValide) {
      enregistrerEchec(emailNormalise);
      const { protectionActive: protectionApres, echecs: echecsApres } = etatProtection(emailNormalise);
      return res.status(401).json({
        message: "Adresse e-mail ou mot de passe incorrect.",
        requiresCaptcha: protectionApres,
        requiresRecaptcha: echecsApres >= 4,
      });
    }

    // Connexion réussie : on efface le compteur d'échecs pour cet email.
    reinitialiserTentatives(emailNormalise);

    const token = jwt.sign(
      { id: utilisateur.id, email: utilisateur.email, role: "super_admin" },
      process.env.JWT_SECRET || "dev_secret_a_remplacer",
      { expiresIn: "8h" }
    );

    return res.json({ token, utilisateur: { id: utilisateur.id, nom: utilisateur.nom, email: utilisateur.email } });
  } catch (err) {
    console.error("Erreur lors de la connexion :", err);
    return res.status(500).json({ message: "Erreur serveur, veuillez réessayer." });
  }
});

export default router;
