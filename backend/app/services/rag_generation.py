"""Génération d'une réponse RAG via le client LLM (Ollama par défaut, OpenAI optionnel).
La recherche et les embeddings restent locaux. Si aucun LLM n'est disponible, retourne None :
l'appelant affiche alors les extraits trouvés, sans prétendre les avoir synthétisés."""
import logging

from app.services import llm_client

logger = logging.getLogger("erp.rag.generation")

SYSTEM_PROMPT = (
    "Tu es l'assistant documentaire d'un ERP. Réponds en {langue}. "
    "Réponds directement et précisément à la question, en une à trois phrases si possible "
    "(idéalement moins de 80 mots). Utilise uniquement les passages fournis et ne recopie pas "
    "les documents entiers. Sélectionne uniquement les détails qui répondent à la question. "
    "Si plusieurs valeurs ou codes apparaissent, distingue-les par leur contexte : "
    "choisis celui dont le nom correspond exactement au terme de la question "
    "(un code de validation n'est pas un code de vérification). "
    "Le titre et le nom de chaque document sont aussi des informations utilisables : "
    "si la question porte sur le NOM ou le titre d'un document ou d'un cours, "
    "réponds à partir des titres des sources, en écrivant le nom proprement "
    "(sans extension de fichier, avec des espaces à la place des tirets bas). "
    "Si la question porte sur le SUJET, le thème ou le contenu d'un document, "
    "résume ce que disent les extraits (titre figurant dans le texte, objectif, idées principales) "
    "au lieu de répéter le nom du fichier. "
    "Ne traduis et ne translittère JAMAIS les noms propres (personnes, entreprises, produits), les codes ni les sigles : "
    "recopie-les exactement comme ils sont écrits dans le document, même si ta réponse est en arabe ou en anglais "
    "(exemple : écris « Pr. Noussair FIKRI », jamais une version arabisée). "
    "Comprends les abréviations courantes : Pr = Professeur, Dr = Docteur, M. = Monsieur, Mme = Madame. "
    "Un nom précédé de « Pr. » dans l'en-tête ou la page de titre est celui du professeur ou de l'auteur du cours. "
    "Si la question est vague, indique les documents qui semblent concernés. "
    "Ignore les passages sans rapport avec la question ; lis-les tous, car le plus pertinent n'est pas toujours le premier. "
    "Si la réponse est une liste (outils, étapes, commandes), donne la liste complète trouvée dans les passages. "
    "Cite la source utilisée avec son titre. "
    "Si ni les titres ni les extraits ne permettent de répondre, commence ta réponse par [NON_TROUVE] "
    "puis dis que l'information n'a pas été trouvée dans les documents disponibles. "
    "Ne devine rien et n'ajoute aucun fait."
)


def _titre_lisible(valeur):
    texte = (valeur or "").strip()
    for extension in (".pdf", ".docx", ".txt", ".doc"):
        if texte.lower().endswith(extension):
            texte = texte[: -len(extension)]
    return texte.replace("_", " ")


def generer_reponse(question: str, sources: list[dict], langue: str) -> str | None:
    if not sources:
        return None
    langue_nom = {"fr": "français", "en": "English", "ar": "العربية"}.get(langue, "français")
    context = "\n\n".join(
        f"Source: {_titre_lisible(item.get('title'))} — {_titre_lisible(item.get('source'))}\nExtrait: {item.get('context') or item.get('excerpt')}"
        for item in sources
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(langue=langue_nom)},
        {"role": "user", "content": f"Question: {question}\n\nContexte documentaire:\n{context}"},
    ]
    try:
        return llm_client.chat_completion(messages, temperature=0.1)
    except llm_client.LLMError as exc:
        if exc.kind not in {"unconfigured", "cooldown"}:
            logger.warning("Génération RAG indisponible (%s); extraits conservés", exc.kind)
        return None


SYSTEM_PROMPT_HORS_DOCUMENTS = (
    "Tu es l'assistant IA d'une plateforme ERP utilisée par différentes entreprises. "
    "Aucun document de l'entreprise ne correspond au message de l'utilisateur. "
    "Réponds dans la langue du message de l'utilisateur (par défaut : {langue}), de façon courte, naturelle et polie. "
    "Règles : "
    "1) Salutations, remerciements, conversation courante (bonjour, bonsoir, merci, comment ça va) : réponds naturellement, "
    "en t'adaptant au moment de la journée ou à la formule utilisée. "
    "2) Questions de culture générale ou d'aide à l'utilisation de l'ERP : réponds simplement et honnêtement. "
    "3) Questions sur l'entreprise de l'utilisateur, ses documents, ses employés, ses chiffres, ses clients ou toute information interne : "
    "tu n'as pas cette information, dis clairement qu'elle n'a pas été trouvée dans les documents disponibles et invite à importer le document concerné. "
    "N'invente jamais un nom, une adresse, un chiffre, un code ou une politique. "
    "Reste bref : pas de conseils génériques ni de références à un « système ». "
    "Le module actuellement affiché est : {module}."
)


def repondre_hors_documents(question: str, langue: str, module_nom: str = "") -> str | None:
    """Réponse du LLM quand aucun passage documentaire n'est pertinent.
    Retourne None si le LLM est indisponible : l'appelant garde alors son comportement de repli."""
    if not (question or "").strip():
        return None
    langue_nom = {"fr": "français", "en": "English", "ar": "العربية"}.get(langue, "français")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_HORS_DOCUMENTS.format(langue=langue_nom, module=module_nom or "inconnu")},
        {"role": "user", "content": question.strip()},
    ]
    try:
        return llm_client.chat_completion(messages, temperature=0.3)
    except llm_client.LLMError as exc:
        if exc.kind not in {"unconfigured", "cooldown"}:
            logger.warning("Réponse hors documents indisponible (%s)", exc.kind)
        return None
