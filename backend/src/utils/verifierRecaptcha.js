// Vérifie le token reCAPTCHA auprès des serveurs de Google. C'est une étape
// obligatoire : un token reCAPTCHA "valide" côté client peut être falsifié
// facilement si on ne le revérifie pas côté serveur.
//
// RECAPTCHA_SECRET_KEY doit être configurée avec la vraie clé secrète du
// site (obtenue gratuitement sur https://www.google.com/recaptcha/admin).
// La clé ci-dessous (par défaut) est la clé de TEST officielle publiée par
// Google : elle valide toujours la requête, pratique en développement,
// mais DOIT être remplacée avant la mise en production.
const SECRET_PAR_DEFAUT_TEST = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe";

export async function verifierRecaptcha(token) {
  if (!token) return false;

  const secret = process.env.RECAPTCHA_SECRET_KEY || SECRET_PAR_DEFAUT_TEST;

  try {
    const res = await fetch("https://www.google.com/recaptcha/api/siteverify", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ secret, response: token }),
    });
    const data = await res.json();
    return data.success === true;
  } catch (err) {
    // Si Google est injoignable, on refuse par défaut (fail-safe côté sécurité).
    console.error("Erreur de vérification reCAPTCHA :", err.message);
    return false;
  }
}
