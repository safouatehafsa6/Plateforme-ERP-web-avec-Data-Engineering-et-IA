import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, User, Building2 } from "lucide-react";
import { apiPost } from "../api/config";
import CaptchaLocal from "../components/CaptchaLocal";
import IndicateurForceMotDePasse from "../components/IndicateurForceMotDePasse";

const DOCUMENTS_PAR_TYPE = {
  personne_physique: [{ id: "cin", labelKey: "doc_cin" }],
  entreprise: [
    { id: "cin_gerant", labelKey: "doc_cin_gerant" },
    { id: "patente", labelKey: "doc_patente" },
    { id: "extrait_rne", labelKey: "doc_extrait_rne" },
  ],
};

// Regex email : présence de "@", d'un domaine valide, aucun espace.
const REGEX_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Inscription() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [etape, setEtape] = useState(0); // 0 = choix du type, 1 = infos, 2 = OTP, 3 = KYC, 4 = plan, 5 = paiement, 6 = fini
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");

  const [typeCompte, setTypeCompte] = useState(null); // "personne_physique" | "entreprise"
  const [entrepriseId, setEntrepriseId] = useState(null);
  const [nomBaseFinal, setNomBaseFinal] = useState("");

  const [form, setForm] = useState({
    nomEntreprise: "", secteur: "", numeroFiscal: "", numeroCin: "", nomAdmin: "",
    email: "", emailConfirmation: "",
    telephone: "",
    motDePasse: "", motDePasseConfirmation: "",
  });
  const [cguAccepte, setCguAccepte] = useState(false);
  const [captchaValeur, setCaptchaValeur] = useState("");
  const captchaRef = useRef(null);

  const [codeOtp, setCodeOtp] = useState("");
  const [documents, setDocuments] = useState({});
  const [planChoisi, setPlanChoisi] = useState(null);

  const ETAPES = [
    t("etape_type"), t("etape_entreprise"), t("etape_verification"),
    t("etape_documents"), t("etape_abonnement"), t("etape_paiement"), t("etape_termine"),
  ];
  const PLANS = [
    { id: "essai", nom: t("plan_essai_nom"), prix: "0 MAD", duree: t("plan_essai_duree"), avantage: t("plan_essai_avantage") },
    { id: "standard", nom: t("plan_standard_nom"), prix: t("plan_standard_prix"), duree: t("plan_standard_duree"), avantage: t("plan_standard_avantage") },
    { id: "premium", nom: t("plan_premium_nom"), prix: t("plan_premium_prix"), duree: t("plan_premium_duree"), avantage: t("plan_premium_avantage") },
  ];

  function majForm(champ, valeur) {
    setForm((f) => ({ ...f, [champ]: valeur }));
  }

  function choisirType(type) {
    setTypeCompte(type);
    setEtape(1);
  }

  // Validation côté client : donne un retour immédiat à l'utilisateur,
  // mais NE REMPLACE PAS la validation côté serveur (le backend revérifie
  // systématiquement tout, conformément au principe "ne jamais faire
  // confiance uniquement au Frontend").
  function validerAvantEnvoi() {
    if (" ".split("").some((c) => form.email.includes(c)) || " ".split("").some((c) => form.emailConfirmation.includes(c))) {
      return "L'adresse email ne doit contenir aucun espace.";
    }
    if (!REGEX_EMAIL.test(form.email.trim())) {
      return "Adresse email invalide.";
    }
    if (form.email.trim().toLowerCase() !== form.emailConfirmation.trim().toLowerCase()) {
      return "Les deux adresses email ne correspondent pas.";
    }
    const mdp = form.motDePasse;
    const politiqueOk =
      mdp.length >= 8 && /[A-Za-zÀ-ÿ]/.test(mdp) && /\d/.test(mdp) && /[^A-Za-zÀ-ÿ0-9]/.test(mdp);
    if (!politiqueOk) {
      return "Le mot de passe doit contenir au moins 8 caractères, avec des lettres, des chiffres et un caractère spécial.";
    }
    if (form.motDePasse !== form.motDePasseConfirmation) {
      return "Les deux mots de passe ne correspondent pas.";
    }
    if (!cguAccepte) {
      return "Vous devez accepter les conditions d'utilisation pour continuer.";
    }
    if (typeCompte === "entreprise" && !form.numeroFiscal.trim()) {
      return "Le numéro d'identification fiscale est obligatoire.";
    }
    if (!form.numeroCin.trim()) {
      return "Le numéro de carte d'identité nationale est obligatoire.";
    }
    return null;
  }

  async function gererInscription(e) {
    e.preventDefault();
    setErreur("");

    const erreurLocale = validerAvantEnvoi();
    if (erreurLocale) {
      setErreur(erreurLocale);
      return;
    }

    setEnCours(true);
    try {
      const data = await apiPost("/entreprises/inscription", {
        ...form,
        typeCompte,
        cguAccepte,
        captchaId: captchaRef.current?.captchaId,
        captchaValeur,
      });
      setEntrepriseId(data.entrepriseId);
      setEtape(2);
    } catch (err) {
      setErreur(err.data?.message || err.message);
      // Un captcha à usage unique doit être renouvelé après tout échec,
      // qu'il vienne du captcha lui-même ou d'une autre validation.
      captchaRef.current?.rafraichir();
      setCaptchaValeur("");
    } finally {
      setEnCours(false);
    }
  }

  async function gererOtp(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      await apiPost("/entreprises/verifier-otp", { entrepriseId, code: codeOtp });
      setEtape(3);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  async function gererRenvoiOtp() {
    setErreur("");
    try {
      const data = await apiPost("/entreprises/renvoyer-otp", { entrepriseId });
      setErreur(data.message);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    }
  }

  async function gererKyc(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      await apiPost("/entreprises/kyc", { entrepriseId, documents });
      setEtape(4);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  async function gererChoixPlan(plan) {
    setPlanChoisi(plan);
    setErreur("");
    setEnCours(true);
    try {
      const data = await apiPost("/entreprises/abonnement", { entrepriseId, plan: plan.id });
      if (data.requiertPaiement) setEtape(5);
      else await activerDirectement();
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  async function activerDirectement() {
    const data = await apiPost("/entreprises/activer-essai", { entrepriseId });
    setNomBaseFinal(data.nomBase);
    setEtape(6);
  }

  async function gererPaiement(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      const data = await apiPost("/entreprises/confirmer-paiement", { entrepriseId });
      setNomBaseFinal(data.nomBase);
      setEtape(6);
    } catch (err) {
      setErreur(err.data?.message || err.message);
    } finally {
      setEnCours(false);
    }
  }

  const documentsAttendus = typeCompte ? DOCUMENTS_PAR_TYPE[typeCompte] : [];
  const tousDocumentsFournis = documentsAttendus.every((d) => documents[d.id]);

  return (
    <div className="inscription-layout">
      <div className="inscription-carte">
        <div className="etapes-indicateur">
          {ETAPES.map((nom, i) => (
            <div key={nom} className={`etape-puce ${i < etape ? "etape-puce--faite" : i === etape ? "etape-puce--active" : ""}`}>
              <span className="etape-puce__rond">{i < etape ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
              <span className="etape-puce__nom">{nom}</span>
            </div>
          ))}
        </div>

        {erreur && <div className="erreur-message">{erreur}</div>}

        {etape === 0 && (
          <div>
            <h1>{t("type_compte_titre")}</h1>
            <p className="connexion-formulaire__soustitre">{t("type_compte_soustitre")}</p>
            <div className="plans-grille">
              <button type="button" className="plan-carte" onClick={() => choisirType("personne_physique")}>
                <User size={22} strokeWidth={1.75} style={{ marginBottom: "0.5rem" }} />
                <div className="plan-carte__nom">{t("type_personne_physique")}</div>
                <p className="plan-carte__avantage">{t("type_personne_physique_desc")}</p>
              </button>
              <button type="button" className="plan-carte" onClick={() => choisirType("entreprise")}>
                <Building2 size={22} strokeWidth={1.75} style={{ marginBottom: "0.5rem" }} />
                <div className="plan-carte__nom">{t("type_entreprise")}</div>
                <p className="plan-carte__avantage">{t("type_entreprise_desc")}</p>
              </button>
            </div>
          </div>
        )}

        {etape === 1 && (
          <form onSubmit={gererInscription}>
            <h1>{t("inscription_titre")}</h1>
            <p className="connexion-formulaire__soustitre">{t("inscription_soustitre")}</p>

            {typeCompte === "entreprise" && (
              <>
                <div className="champ">
                  <label>{t("label_nom_entreprise")}</label>
                  <input value={form.nomEntreprise} onChange={(e) => majForm("nomEntreprise", e.target.value)} required />
                </div>
                <div className="champ">
                  <label>{t("label_secteur")}</label>
                  <input value={form.secteur} onChange={(e) => majForm("secteur", e.target.value)} placeholder={t("secteur_placeholder")} />
                </div>
                <div className="champ">
                  <label>{t("label_numero_fiscal")}</label>
                  <input value={form.numeroFiscal} onChange={(e) => majForm("numeroFiscal", e.target.value)} required />
                </div>
              </>
            )}
            <div className="champ">
              <label>{typeCompte === "entreprise" ? t("label_nom_representant") : t("label_nom_complet")}</label>
              <input value={form.nomAdmin} onChange={(e) => majForm("nomAdmin", e.target.value)} required />
            </div>
            <div className="champ">
              <label>{t("label_numero_cin")}</label>
              <input value={form.numeroCin} onChange={(e) => majForm("numeroCin", e.target.value)} required />
            </div>

            <div className="champ">
              <label>{t("email")}</label>
              <input type="email" value={form.email} onChange={(e) => majForm("email", e.target.value)} required />
            </div>
            <div className="champ">
              <label>{t("label_confirmation_email")}</label>
              <input
                type="email"
                value={form.emailConfirmation}
                onChange={(e) => majForm("emailConfirmation", e.target.value)}
                onPaste={(e) => e.preventDefault()}
                required
              />
              <span className="champ__aide">{t("aide_pas_de_copier_coller")}</span>
            </div>

            <div className="champ">
              <label>{t("label_telephone")}</label>
              <input value={form.telephone} onChange={(e) => majForm("telephone", e.target.value)} />
            </div>

            <div className="champ">
              <label>{t("mot_de_passe")}</label>
              <input
                type="password"
                value={form.motDePasse}
                onChange={(e) => majForm("motDePasse", e.target.value)}
                required
                minLength={8}
              />
              <IndicateurForceMotDePasse motDePasse={form.motDePasse} />
            </div>
            <div className="champ">
              <label>{t("label_confirmation_mot_de_passe")}</label>
              <input
                type="password"
                value={form.motDePasseConfirmation}
                onChange={(e) => majForm("motDePasseConfirmation", e.target.value)}
                onPaste={(e) => e.preventDefault()}
                required
              />
            </div>

            <CaptchaLocal
              ref={captchaRef}
              endpoint="/entreprises/captcha"
              valeur={captchaValeur}
              onChangeValeur={setCaptchaValeur}
            />

            <label className="case-cgu">
              <input
                type="checkbox"
                checked={cguAccepte}
                onChange={(e) => setCguAccepte(e.target.checked)}
              />
              <span>{t("texte_acceptation_cgu")}</span>
            </label>

            <button className="bouton-principal" disabled={enCours}>{enCours ? "..." : t("bouton_continuer")}</button>
          </form>
        )}

        {etape === 2 && (
          <form onSubmit={gererOtp}>
            <h1>{t("verification_titre")}</h1>
            <p className="connexion-formulaire__soustitre">{t("verification_soustitre", { email: form.email })}</p>
            <div className="champ">
              <label>{t("label_code_verification")}</label>
              <input value={codeOtp} onChange={(e) => setCodeOtp(e.target.value)} maxLength={6} required />
            </div>
            <button className="bouton-principal" disabled={enCours}>{enCours ? "..." : t("bouton_verifier")}</button>
            <button type="button" className="lien-secondaire" onClick={gererRenvoiOtp} style={{ display: "block", background: "none", border: "none", cursor: "pointer" }}>
              {t("bouton_renvoyer_code")}
            </button>
          </form>
        )}

        {etape === 3 && (
          <form onSubmit={gererKyc}>
            <h1>{t("kyc_titre")}</h1>
            <p className="connexion-formulaire__soustitre">
              {typeCompte === "entreprise" ? t("kyc_soustitre_entreprise") : t("kyc_soustitre_personne")}
            </p>
            {documentsAttendus.map((doc) => (
              <div className="champ" key={doc.id}>
                <label>{t(doc.labelKey)}</label>
                <input
                  type="file"
                  onChange={(e) => setDocuments((d) => ({ ...d, [doc.id]: e.target.files?.[0]?.name || "" }))}
                  required
                />
              </div>
            ))}
            <button className="bouton-principal" disabled={enCours || !tousDocumentsFournis}>
              {enCours ? "..." : t("bouton_soumettre")}
            </button>
          </form>
        )}

        {etape === 4 && (
          <div>
            <h1>{t("abonnement_titre")}</h1>
            <p className="connexion-formulaire__soustitre">{t("abonnement_soustitre")}</p>
            <div className="plans-grille">
              {PLANS.map((plan) => (
                <button key={plan.id} type="button" className="plan-carte" onClick={() => gererChoixPlan(plan)} disabled={enCours}>
                  <div className="plan-carte__nom">{plan.nom}</div>
                  <div className="plan-carte__prix">{plan.prix}</div>
                  <div className="plan-carte__duree">{plan.duree}</div>
                  <p className="plan-carte__avantage">{plan.avantage}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {etape === 5 && (
          <form onSubmit={gererPaiement}>
            <h1>{t("paiement_titre")}</h1>
            <p className="connexion-formulaire__soustitre">
              {t("paiement_plan_selectionne", { plan: planChoisi?.nom, prix: planChoisi?.prix })}
            </p>
            <div className="champ">
              <label>{t("label_numero_carte")}</label>
              <input placeholder="4242 4242 4242 4242" required />
            </div>
            <div className="champ-ligne">
              <div className="champ"><label>{t("label_expiration")}</label><input placeholder="MM/AA" required /></div>
              <div className="champ"><label>{t("label_cvc")}</label><input placeholder="123" required /></div>
            </div>
            <p className="plan-carte__avantage">{t("texte_paiement_simule")}</p>
            <button className="bouton-principal" disabled={enCours}>{enCours ? "..." : t("bouton_payer")}</button>
          </form>
        )}

        {etape === 6 && (
          <div className="confirmation-finale">
            <div className="confirmation-finale__icone"><Check size={28} strokeWidth={3} /></div>
            <h1>{t("termine_titre")}</h1>
            <p className="connexion-formulaire__soustitre">{t("termine_soustitre", { nomBase: nomBaseFinal })}</p>
            <button className="bouton-principal" onClick={() => navigate("/")}>{t("bouton_se_connecter_maintenant")}</button>
          </div>
        )}
      </div>
    </div>
  );
}
