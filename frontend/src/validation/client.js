const EMAIL_PATTERN = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;
const PHONE_PATTERN = /^\+?[0-9\s().\/-]+$/;

/** Normalise les champs du formulaire et ne transmet que les propriétés attendues par l'API. */
export function normaliserClient(values = {}) {
  return {
    nom: String(values.nom ?? "").trim(),
    email: String(values.email ?? "").trim() || null,
    telephone: String(values.telephone ?? "").trim() || null,
    adresse: String(values.adresse ?? "").trim() || null,
  };
}

/** Retourne les erreurs par nom de champ ; les champs facultatifs peuvent rester vides. */
export function validerClient(values = {}) {
  const client = normaliserClient(values);
  const erreurs = {};

  if (!client.nom) {
    erreurs.nom = "Le nom du client est obligatoire.";
  } else if (client.nom.length > 150) {
    erreurs.nom = "Le nom ne peut pas dépasser 150 caractères.";
  }

  if (client.email) {
    if (client.email.length > 150) {
      erreurs.email = "L’adresse e-mail ne peut pas dépasser 150 caractères.";
    } else if (!EMAIL_PATTERN.test(client.email)) {
      erreurs.email = "Saisissez une adresse e-mail valide, par exemple nom@entreprise.com.";
    }
  }

  if (client.telephone) {
    if (client.telephone.length > 30) {
      erreurs.telephone = "Le téléphone ne peut pas dépasser 30 caractères.";
    } else if (!PHONE_PATTERN.test(client.telephone)) {
      erreurs.telephone = "Utilisez uniquement des chiffres, un + initial, des espaces ou les séparateurs ( ) . / -.";
    } else {
      const nombreChiffres = client.telephone.replace(/\D/g, "").length;
      if (nombreChiffres < 7 || nombreChiffres > 15) {
        erreurs.telephone = "Le numéro doit contenir entre 7 et 15 chiffres.";
      }
    }
  }

  if (client.adresse && client.adresse.length > 1000) {
    erreurs.adresse = "L’adresse ne peut pas dépasser 1000 caractères.";
  }

  return erreurs;
}


/** Propose une correction simple des fautes de domaine e-mail les plus courantes. */
export function suggererCorrectionEmail(value = "") {
  const email = String(value).trim();
  const match = email.match(/^([^\s@]+)@([^\s@]+)$/);
  if (!match) return null;
  const domaines = {
    "gmal.com": "gmail.com", "gmial.com": "gmail.com", "gmai.com": "gmail.com",
    "gmail.con": "gmail.com", "gmail.co": "gmail.com", "gmail.fr": "gmail.com",
    "hotnail.com": "hotmail.com", "hotmai.com": "hotmail.com", "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com", "outloo.com": "outlook.com", "yaho.com": "yahoo.com",
  };
  const domaine = match[2].toLowerCase();
  const correction = domaines[domaine];
  return correction ? `${match[1]}@${correction}` : null;
}
