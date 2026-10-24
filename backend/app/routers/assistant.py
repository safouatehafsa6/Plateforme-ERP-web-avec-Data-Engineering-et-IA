
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from decimal import Decimal
from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

MODULES = {
    "dashboard": "Tableau de bord",
    "ventes": "Ventes",
    "achats": "Achats",
    "fournisseurs": "Fournisseurs",
    "clients": "Clients",
    "stock": "Stock",
    "facturation": "Facturation",
    "comptabilite": "Comptabilité",
    "parametres": "Paramètres",
    "collaborateurs": "Collaborateurs",
    "roles-permissions": "Rôles & Permissions",
    "utilisateurs-externes": "Utilisateurs externes",
}


class AssistantState(BaseModel):
    operation: str | None = None
    step: str | None = None
    data: dict = Field(default_factory=dict)


class AssistantMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    langue: str = Field(default="fr", pattern="^(fr|en|ar)$")
    module: str = Field(default="dashboard", max_length=100)
    state: AssistantState = Field(default_factory=AssistantState)


def _fmt(value):
    return float(value) if isinstance(value, Decimal) else value


def _pool(user):
    return get_pool_entreprise(user["nomBase"])


def _has_permission(user, module, action="consulter"):
    if user.get("role") == "Admin":
        return True

    uid = user.get("id")
    if not uid or not user.get("nomBase") or user.get("type") == "externe":
        return False

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM utilisateur u
                JOIN role_permission rp ON rp.role_id = u.role_id
                JOIN permission p ON p.id = rp.permission_id
                WHERE u.id = %s
                  AND u.actif = TRUE
                  AND p.module = %s
                  AND p.action = %s
                LIMIT 1
                """,
                (uid, module, action),
            )
            return cur.fetchone() is not None
    finally:
        pool.putconn(conn)


def _denied(langue, module, action="consulter"):
    if langue == "en":
        return (
            "I cannot perform this operation because your account does not "
            f"have the required permission ({module}.{action})."
        )
    if langue == "ar":
        return (
            "لا يمكنني تنفيذ هذه العملية لأن حسابك لا يملك "
            f"الصلاحية المطلوبة ({module}.{action})."
        )
    return (
        "Je ne peux pas effectuer cette opération car votre compte "
        f"ne possède pas la permission requise ({module}.{action})."
    )


def _entity_meta(entity):
    return (
        ("clients", "client")
        if entity == "client"
        else ("fournisseurs", "fournisseur")
    )


def _create_entity(user, entity, data):
    module, table = _entity_meta(entity)

    if not _has_permission(user, module, "creer"):
        raise HTTPException(403, _denied("fr", module, "creer"))

    nom = (data.get("nom") or "").strip()
    if not nom:
        raise HTTPException(422, "Le nom est obligatoire.")

    vals = {
        k: ((data.get(k) or "").strip() or None)
        for k in ("email", "telephone", "adresse")
    }

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM {table} WHERE LOWER(nom)=LOWER(%s) LIMIT 1",
                (nom,),
            )
            if cur.fetchone():
                raise HTTPException(
                    409, f"Un {entity} portant ce nom existe déjà."
                )

            cur.execute(
                f"""
                INSERT INTO {table} (nom, email, telephone, adresse)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nom, email, telephone, adresse
                """,
                (nom, vals["email"], vals["telephone"], vals["adresse"]),
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))

        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _find_entity(user, entity, query):
    module, table = _entity_meta(entity)

    if not _has_permission(user, module, "consulter"):
        raise HTTPException(403, _denied("fr", module, "consulter"))

    q = (query or "").strip()
    if not q:
        return []

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, nom, email, telephone, adresse
                FROM {table}
                WHERE nom ILIKE %s
                   OR COALESCE(email, '') ILIKE %s
                   OR COALESCE(telephone, '') ILIKE %s
                ORDER BY nom
                LIMIT 10
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [
                dict(zip(cols, [_fmt(v) for v in row]))
                for row in rows
            ]
    finally:
        pool.putconn(conn)


def _update_entity(user, entity, entity_id, field, value):
    module, table = _entity_meta(entity)

    if not _has_permission(user, module, "modifier"):
        raise HTTPException(403, _denied("fr", module, "modifier"))

    allowed = {"nom", "email", "telephone", "adresse"}
    if field not in allowed:
        raise HTTPException(422, "Champ de modification non autorisé.")

    value = (value or "").strip() or None
    if field == "nom" and not value:
        raise HTTPException(422, "Le nom est obligatoire.")

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if field == "nom":
                cur.execute(
                    f"""
                    SELECT 1 FROM {table}
                    WHERE LOWER(nom)=LOWER(%s) AND id<>%s
                    LIMIT 1
                    """,
                    (value, entity_id),
                )
                if cur.fetchone():
                    raise HTTPException(
                        409, "Un autre enregistrement porte déjà ce nom."
                    )

            cur.execute(
                f"""
                UPDATE {table}
                SET {field}=%s
                WHERE id=%s
                RETURNING id, nom, email, telephone, adresse
                """,
                (value, entity_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Enregistrement introuvable.")

            result = dict(zip([d[0] for d in cur.description], row))

        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _search_products(user, query):
    if not _has_permission(user, "stock", "consulter"):
        raise HTTPException(403, _denied("fr", "stock", "consulter"))

    q = (query or "").strip()
    if not q:
        return []

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, reference, nom, categorie, prix_unitaire,
                       COALESCE(stock_actuel, 0) AS stock_actuel
                FROM produit
                WHERE reference ILIKE %s OR nom ILIKE %s
                ORDER BY nom
                LIMIT 10
                """,
                (f"%{q}%", f"%{q}%"),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [
                dict(zip(cols, [_fmt(v) for v in row]))
                for row in rows
            ]
    finally:
        pool.putconn(conn)


def _format_products(rows, lang):
    if not rows:
        return (
            "Aucun produit correspondant n’a été trouvé."
            if lang == "fr"
            else "No matching product was found."
            if lang == "en"
            else "لم يتم العثور على منتج مطابق."
        )

    if lang == "en":
        lines = [
            f"- {r['nom']} | Ref: {r['reference']} | "
            f"Price: {r['prix_unitaire']:.2f} | Stock: {r['stock_actuel']}"
            for r in rows
        ]
    elif lang == "ar":
        lines = [
            f"- {r['nom']} | المرجع: {r['reference']} | "
            f"السعر: {r['prix_unitaire']:.2f} | المخزون: {r['stock_actuel']}"
            for r in rows
        ]
    else:
        lines = [
            f"- {r['nom']} | Réf: {r['reference']} | "
            f"Prix: {r['prix_unitaire']:.2f} | Stock: {r['stock_actuel']}"
            for r in rows
        ]

    intro = (
        "Produits trouvés:\n"
        if lang == "fr"
        else "Products found:\n"
        if lang == "en"
        else "المنتجات التي تم العثور عليها:\n"
    )
    return intro + "\n".join(lines)


def _create_order(user, client_id, lines):
    if not _has_permission(user, "ventes", "creer"):
        raise HTTPException(403, _denied("fr", "ventes", "creer"))

    if not _has_permission(user, "stock", "consulter"):
        raise HTTPException(403, _denied("fr", "stock", "consulter"))

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client WHERE id=%s", (client_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Client introuvable.")

            total = Decimal("0")
            normalized = []

            for line in lines:
                cur.execute(
                    """
                    SELECT id, nom, prix_unitaire,
                           COALESCE(stock_actuel, 0)
                    FROM produit WHERE id=%s
                    """,
                    (line["produit_id"],),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Produit introuvable.")

                if row[3] < line["quantite"]:
                    raise HTTPException(
                        400,
                        f"Stock insuffisant pour {row[1]} : "
                        f"disponible {row[3]}, demandé {line['quantite']}.",
                    )

                total += Decimal(str(row[2])) * line["quantite"]
                normalized.append((row[0], line["quantite"], row[2]))

            total = total.quantize(Decimal("0.01"))

            cur.execute("SELECT nextval('seq_commande_numero')")
            numero = (
                f"CMD-{__import__('datetime').datetime.now().year}-"
                f"{cur.fetchone()[0]:06d}"
            )

            cur.execute(
                """
                INSERT INTO commande (client_id, statut, montant_total, numero)
                VALUES (%s, 'confirmee', %s, %s)
                RETURNING id
                """,
                (client_id, total, numero),
            )
            commande_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO ligne_commande
                    (commande_id, produit_id, quantite, prix_unitaire)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (commande_id, pid, q, pu)
                    for pid, q, pu in normalized
                ],
            )

        conn.commit()
        return {
            "id": commande_id,
            "numero": numero,
            "total": float(total),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _create_invoice(user, commande_id):
    if not _has_permission(user, "facturation", "creer"):
        raise HTTPException(403, _denied("fr", "facturation", "creer"))

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, numero FROM facture
                WHERE commande_id=%s ORDER BY id LIMIT 1
                """,
                (commande_id,),
            )
            existing = cur.fetchone()
            if existing:
                return {"id": existing[0], "numero": existing[1]}

            cur.execute(
                "SELECT montant_total, statut FROM commande WHERE id=%s",
                (commande_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Commande introuvable.")

            cur.execute("SELECT nextval('seq_facture_numero')")
            numero = (
                f"FAC-{__import__('datetime').datetime.now().year}-"
                f"{cur.fetchone()[0]:06d}"
            )

            cur.execute(
                """
                INSERT INTO facture
                    (commande_id, numero, montant_total, statut, code_verification)
                VALUES (%s, %s, %s, 'impayee',
                        encode(gen_random_bytes(24), 'hex'))
                RETURNING id
                """,
                (commande_id, numero, row[0]),
            )
            fid = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO ligne_facture
                    (facture_id, produit_id, designation, quantite,
                     prix_unitaire, remise_pct)
                SELECT %s, lc.produit_id, p.nom, lc.quantite,
                       lc.prix_unitaire, 0
                FROM ligne_commande lc
                JOIN produit p ON p.id=lc.produit_id
                WHERE lc.commande_id=%s
                """,
                (fid, commande_id),
            )

        conn.commit()
        return {"id": fid, "numero": numero}
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _is_yes(m):
    return m.strip().lower() in {
        "oui", "yes", "y", "ok", "d'accord", "daccord",
        "confirmer", "confirme", "نعم", "موافق",
    }


def _is_no(m):
    return m.strip().lower() in {
        "non", "no", "n", "annuler", "annule", "cancel",
        "لا", "إلغاء", "الغاء",
    }


def _is_skip(m):
    return m.strip().lower() in {
        "passer", "skip", "aucun", "aucune", "لا",
        "تخطي", "تخطى",
    }


def _prompts(lang):
    if lang == "en":
        return {
            "nom": "What is the name?",
            "email": "What is the email? (optional — type 'skip')",
            "telephone": "What is the phone number? (optional — type 'skip')",
            "adresse": "What is the address? (optional — type 'skip')",
            "confirm": "Please confirm. Do you want to create it? (yes/no)",
            "search": "What client/supplier name should I search for?",
            "field": "Which field do you want to modify: name, email, phone or address?",
            "value": "What is the new value?",
            "editconfirm": "Please confirm this modification (yes/no).",
            "order_client": "Which customer should be used for the order?",
            "order_product": "Which product would you like to add?",
            "order_qty": "What quantity would you like to order?",
            "order_more": "Would you like to add another product? (yes/no)",
            "order_confirm": "Here is the order summary. Confirm creation? (yes/no)",
            "invoice": "The order was created. Would you like to prepare the invoice now? (yes/no)",
        }

    if lang == "ar":
        return {
            "nom": "ما الاسم؟",
            "email": "ما البريد الإلكتروني؟ (اختياري — اكتب تخطي)",
            "telephone": "ما رقم الهاتف؟ (اختياري — اكتب تخطي)",
            "adresse": "ما العنوان؟ (اختياري — اكتب تخطي)",
            "confirm": "راجع المعلومات. هل تريد إنشاء السجل؟ (نعم/لا)",
            "search": "ما اسم العميل أو المورد الذي تريد البحث عنه؟",
            "field": "ما الحقل الذي تريد تعديله: الاسم أو البريد أو الهاتف أو العنوان؟",
            "value": "ما القيمة الجديدة؟",
            "editconfirm": "هل تؤكد هذا التعديل؟ (نعم/لا)",
            "order_client": "ما العميل الذي تريد إنشاء الطلب له؟",
            "order_product": "ما المنتج الذي تريد إضافته؟",
            "order_qty": "ما الكمية التي تريد طلبها؟",
            "order_more": "هل تريد إضافة منتج آخر؟ (نعم/لا)",
            "order_confirm": "هذا هو ملخص الطلب. هل تريد تأكيد إنشائه؟ (نعم/لا)",
            "invoice": "تم إنشاء الطلب. هل تريد إعداد الفاتورة الآن؟ (نعم/لا)",
        }

    return {
        "nom": "Quel est le nom ?",
        "email": "Quel est l’e-mail ? (facultatif — écrivez « passer »)",
        "telephone": "Quel est le téléphone ? (facultatif — écrivez « passer »)",
        "adresse": "Quelle est l’adresse ? (facultatif — écrivez « passer »)",
        "confirm": "Voici le récapitulatif. Voulez-vous confirmer la création ? (oui/non)",
        "search": "Quel nom de client ou de fournisseur souhaitez-vous rechercher ?",
        "field": "Quel champ souhaitez-vous modifier : nom, e-mail, téléphone ou adresse ?",
        "value": "Quelle est la nouvelle valeur ?",
        "editconfirm": "Confirmez-vous cette modification ? (oui/non)",
        "order_client": "Quel client souhaitez-vous utiliser pour la commande ?",
        "order_product": "Quel produit souhaitez-vous ajouter ?",
        "order_qty": "Quelle quantité souhaitez-vous commander ?",
        "order_more": "Voulez-vous ajouter un autre produit ? (oui/non)",
        "order_confirm": "Voici le récapitulatif de la commande. Voulez-vous confirmer la création ? (oui/non)",
        "invoice": "La commande a été créée. Voulez-vous préparer la facture maintenant ? (oui/non)",
    }


def _label(entity, lang):
    if lang == "en":
        return "customer" if entity == "client" else "supplier"
    if lang == "ar":
        return "العميل" if entity == "client" else "المورد"
    return "client" if entity == "client" else "fournisseur"


def _summary(entity, data, lang):
    label = _label(entity, lang)
    missing = {
        "fr": "non renseigné",
        "en": "not provided",
        "ar": "غير محدد",
    }

    def v(k):
        return data.get(k) or missing[lang]

    if lang == "en":
        return (
            f"Summary for {label}:\n"
            f"- Name: {v('nom')}\n"
            f"- Email: {v('email')}\n"
            f"- Phone: {v('telephone')}\n"
            f"- Address: {v('adresse')}"
        )
    if lang == "ar":
        return (
            f"ملخص {label}:\n"
            f"- الاسم: {v('nom')}\n"
            f"- البريد: {v('email')}\n"
            f"- الهاتف: {v('telephone')}\n"
            f"- العنوان: {v('adresse')}"
        )
    return (
        f"Récapitulatif du {label} :\n"
        f"- Nom : {v('nom')}\n"
        f"- E-mail : {v('email')}\n"
        f"- Téléphone : {v('telephone')}\n"
        f"- Adresse : {v('adresse')}"
    )


def _format_search(rows, entity, lang):
    if not rows:
        return {
            "fr": f"Aucun {entity} correspondant n’a été trouvé.",
            "en": (
                "No matching customer was found."
                if entity == "client"
                else "No matching supplier was found."
            ),
            "ar": (
                "لم يتم العثور على عميل مطابق."
                if entity == "client"
                else "لم يتم العثور على مورد مطابق."
            ),
        }[lang]

    lines = [
        f"- {r['nom']} | {r.get('email') or '-'} | "
        f"{r.get('telephone') or '-'} | {r.get('adresse') or '-'}"
        for r in rows
    ]

    if lang == "en":
        return "Search results:\n" + "\n".join(lines)
    if lang == "ar":
        return "نتائج البحث:\n" + "\n".join(lines)
    return "Résultats de recherche :\n" + "\n".join(lines)


def _normalize_nlu_text(value):
    """Normalise les accents et la ponctuation pour le fallback NLU."""
    import re
    import unicodedata

    text = (
        (value or "")
        .lower()
        .replace("’", "'")
        .replace("œ", "oe")
        .replace("æ", "ae")
    )
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    text = re.sub(r"[^\w\s@.+/-]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _fallback_understanding(message):
    """Classification multilingue déterministe si aucun LLM n'est disponible."""
    import re

    m = _normalize_nlu_text(message)
    result = {
        "intent": None,
        "entities": {},
        "confidence": 0.0,
        "source": "rules",
    }

    order_terms = (
        "commande", "commandes", "order", "orders", "طلب", "طلبات",
    )
    order_actions = (
        "creer", "creation", "ajouter", "ajoute", "faire", "passer",
        "preparer", "etablir", "lancer", "enregistrer", "commander",
        "je veux", "je voudrais", "j'aimerais", "j ai besoin",
        "make", "place", "create", "prepare", "need", "want to",
        "add", "new", "please create", "إنشاء", "انشاء", "اضافة",
        "أريد", "اريد", "طلب جديد", "انشاء طلب", "إنشاء طلب",
    )
    client_terms = (
        "client", "clients", "customer", "customers",
        "عميل", "عملاء", "زبون", "زبائن",
    )
    supplier_terms = (
        "fournisseur", "fournisseurs", "supplier", "suppliers",
        "مورد", "موردين",
    )
    create_terms = (
        "creer", "creation", "ajouter", "ajoute", "nouveau",
        "nouvelle", "add", "create", "new", "enregistrer",
        "إنشاء", "انشاء", "اضافة", "إضافة",
    )
    search_terms = (
        "chercher", "rechercher", "recherche", "trouver", "cherche",
        "find", "search", "look for", "consulter", "afficher",
        "montre", "liste", "بحث", "ابحث", "البحث", "عرض",
    )
    edit_terms = (
        "modifier", "modifie", "modification", "edit", "update",
        "change", "changer", "mettre a jour", "تعديل", "عدل", "تغيير",
    )

    has_order = any(term in m for term in order_terms)
    has_action = any(term in m for term in order_actions)

    if has_order and (
        has_action
        or re.search(
            r"\b(une|la|nouvelle|une nouvelle|une commande)\b.*\bcommande\b",
            m,
        )
    ):
        result.update(intent="create_commande", confidence=0.78)
    else:
        entity = (
            "client"
            if any(term in m for term in client_terms)
            else "fournisseur"
            if any(term in m for term in supplier_terms)
            else None
        )

        if entity:
            if any(term in m for term in create_terms) or (
                entity == "client"
                and re.search(r"\b(creer|ajouter|faire)\b.*\b(client|customer)\b", m)
            ):
                result.update(intent=f"create_{entity}", confidence=0.75)
            elif any(term in m for term in edit_terms):
                result.update(intent=f"edit_{entity}", confidence=0.75)
            elif any(term in m for term in search_terms):
                result.update(intent=f"search_{entity}", confidence=0.72)

    quantity = re.search(
        r"\b(\d{1,7})\b\s*(?:unites?|pieces?|pcs?)?", m
    )
    if quantity:
        result["entities"]["quantity"] = int(quantity.group(1))

    email = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", message or "")
    if email:
        result["entities"]["email"] = email.group(0)

    client_match = re.search(
        r"(?:\b(?:pour|du|de|au|client)\b)\s+"
        r"(?:le\s+)?(?:client\s+)?[«\"']?"
        r"([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",
        message or "",
        re.IGNORECASE,
    )
    if client_match and result["intent"] == "create_commande":
        candidate = client_match.group(1).strip(" .,'\"»")
        stop_words = (
            "avec", "et", "pour", "produit", "article",
            "quantite", "quantité", "de", "du",
        )
        candidate = re.split(
            r"\s+(?:" + "|".join(stop_words) + r")\s+",
            candidate,
            flags=re.IGNORECASE,
        )[0].strip()

        if candidate and candidate.lower() not in {
            "une", "un", "commande", "client", "mon", "ma", "mes",
        }:
            result["entities"]["client_name"] = candidate

    product_match = re.search(
        r"(?:produit|article)\s+(?:nomme\s+|appele\s+)?"
        r"[«\"']?([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",
        message or "",
        re.IGNORECASE,
    )
    if product_match and result["intent"] == "create_commande":
        result["entities"]["product_name"] = re.split(
            r"\s+(?:pour|avec|quantite|quantité|et)\s+",
            product_match.group(1),
            flags=re.IGNORECASE,
        )[0].strip(" .,'\"»")

    named_match = re.search(
        r"(?:nomme|nommé|nommee|nommée|appele|appelé|appelee|appelée|"
        r"named|name is)\s+[«\"']?([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",
        message or "",
        re.IGNORECASE,
    )
    if named_match:
        candidate = re.split(
            r"\s+(?:avec|et|email|e-mail|telephone|téléphone|adresse|phone)\s+",
            named_match.group(1),
            flags=re.IGNORECASE,
        )[0].strip(" .,'\"»")

        if result["intent"] == "create_client":
            result["entities"]["client_name"] = candidate
        elif result["intent"] == "create_fournisseur":
            result["entities"]["supplier_name"] = candidate

    return result


def _understand_message(message, langue="fr"):
    """Utilise un LLM facultatif pour classifier les intentions et extraire les entités."""
    import json
    import os
    import re
    import httpx

    fallback = _fallback_understanding(message)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback

    allowed = {
        "create_commande", "create_client", "create_fournisseur",
        "edit_client", "edit_fournisseur", "search_client",
        "search_fournisseur", "analytics", "general", None,
    }

    base_url = os.getenv(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    system = (
        "Tu es un classificateur NLU pour un ERP. Tu ne réponds pas à "
        "l'utilisateur et n'exécutes aucune action. Retourne exclusivement "
        "un objet JSON valide avec les clés intent, entities, confidence. "
        "intent doit être l'une de: create_commande, create_client, "
        "create_fournisseur, edit_client, edit_fournisseur, search_client, "
        "search_fournisseur, analytics, general, null. entities est un objet "
        "pouvant contenir client_name, product_name, quantity (entier), email, "
        "phone, address, field, value. N'invente aucune information. "
        "Interprète les paraphrases en français, anglais et arabe, notamment "
        "'créer une commande', 'faire une commande', 'passer une commande' "
        "et 'je voudrais commander' comme create_commande. Si la demande est "
        "ambiguë ou ne correspond pas à une action supportée, choisis general "
        "ou null."
    )

    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"message": message, "langue": langue},
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            timeout=5.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(
            re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                content.strip(),
                flags=re.IGNORECASE,
            )
        )

        intent = parsed.get("intent")
        if intent not in allowed:
            return fallback

        if intent in {"general", "analytics"}:
            intent = None

        entities = (
            parsed.get("entities")
            if isinstance(parsed.get("entities"), dict)
            else {}
        )
        safe_entities = {}

        for key in (
            "client_name", "product_name", "email", "phone",
            "address", "field", "value",
        ):
            value = entities.get(key)
            if isinstance(value, str) and value.strip():
                safe_entities[key] = value.strip()[:200]

        quantity = entities.get("quantity")
        if isinstance(quantity, int) and 0 < quantity <= 1000000:
            safe_entities["quantity"] = quantity

        confidence = parsed.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        if intent not in {None, "general", "analytics"} and confidence < 0.55:
            return fallback

        return {
            "intent": intent,
            "entities": safe_entities,
            "confidence": confidence,
            "source": "llm",
        }
    except Exception:
        return fallback


def _intent(m):
    """Wrapper rétrocompatible utilisé par les anciens tests."""
    return _fallback_understanding(m).get("intent")


def _answer_data(message, langue, user):
    m = message.lower().strip()

    if any(k in m for k in [
        "client", "clients", "customer", "customers",
        "زبون", "زبائن", "عميل", "عملاء",
    ]):
        if not _has_permission(user, "clients"):
            return _denied(langue, "clients")

        pool = _pool(user)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM client")
                count = cur.fetchone()[0]
                cur.execute("SELECT nom FROM client ORDER BY nom LIMIT 10")
                names = [r[0] for r in cur.fetchall()]

            if langue == "en":
                return (
                    f"There are {count} clients. First names: "
                    f"{', '.join(names) if names else 'none'}."
                )
            if langue == "ar":
                return (
                    f"يوجد {count} عميلاً. من الأسماء الأولى: "
                    f"{', '.join(names) if names else 'لا يوجد'}."
                )
            return (
                f"Il y a {count} client(s). Premiers noms : "
                f"{', '.join(names) if names else 'aucun'}."
            )
        finally:
            pool.putconn(conn)

    if any(k in m for k in [
        "fournisseur", "fournisseurs", "supplier", "suppliers",
        "مورد", "موردين",
    ]):
        if not _has_permission(user, "fournisseurs"):
            return _denied(langue, "fournisseurs")

        pool = _pool(user)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM fournisseur")
                count = cur.fetchone()[0]
                cur.execute("SELECT nom FROM fournisseur ORDER BY nom LIMIT 10")
                names = [r[0] for r in cur.fetchall()]

            if langue == "en":
                return (
                    f"There are {count} suppliers. First names: "
                    f"{', '.join(names) if names else 'none'}."
                )
            if langue == "ar":
                return (
                    f"يوجد {count} مورّد(ين). من الأسماء الأولى: "
                    f"{', '.join(names) if names else 'لا يوجد'}."
                )
            return (
                f"Il y a {count} fournisseur(s). Premiers noms : "
                f"{', '.join(names) if names else 'aucun'}."
            )
        finally:
            pool.putconn(conn)

    if any(k in m for k in [
        "stock", "inventaire", "inventory", "produit", "products",
        "product", "مخزون", "مخزن", "منتج",
    ]):
        if not _has_permission(user, "stock"):
            return _denied(langue, "stock")

        pool = _pool(user)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*),
                           COALESCE(SUM(
                               CASE WHEN COALESCE(stock_actuel, 0) <= 0
                               THEN 1 ELSE 0 END
                           ), 0)
                    FROM produit
                    """
                )
                total, rupture = cur.fetchone()

                cur.execute(
                    """
                    SELECT nom, COALESCE(stock_actuel, 0)
                    FROM produit
                    WHERE COALESCE(stock_actuel, 0) <= 5
                    ORDER BY stock_actuel, nom
                    LIMIT 10
                    """
                )
                low = cur.fetchall()

            lowtxt = (
                ", ".join(f"{n} ({s})" for n, s in low)
                if low
                else ("none" if langue == "en" else "aucun")
            )

            if langue == "en":
                return (
                    f"Stock contains {total} products. {rupture} are at "
                    f"zero or below. Low-stock products (<=5): {lowtxt}."
                )
            if langue == "ar":
                return (
                    f"المخزون يحتوي على {total} منتجاً. عدد المنتجات التي "
                    f"مخزونها صفر أو أقل هو {rupture}. المنتجات ذات المخزون "
                    f"المنخفض (<=5): {lowtxt}."
                )
            return (
                f"Le stock contient {total} produit(s). {rupture} sont à "
                f"zéro ou en dessous. Produits à faible stock (<=5) : {lowtxt}."
            )
        finally:
            pool.putconn(conn)

    if any(k in m for k in [
        "facture", "factures", "invoice", "invoices", "billing",
        "impay", "payée", "payees", "فاتورة", "فواتير",
    ]):
        if not _has_permission(user, "facturation"):
            return _denied(langue, "facturation")

        pool = _pool(user)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*),
                           COALESCE(SUM(CASE WHEN statut='impayee' THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN statut='payee' THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN statut='impayee' THEN montant_total ELSE 0 END), 0)
                    FROM facture
                    """
                )
                total, unpaid, paid, amount = cur.fetchone()

            if langue == "en":
                return (
                    f"There are {total} invoices: {paid} paid and {unpaid} "
                    f"unpaid. Unpaid amount: {float(amount):.2f}."
                )
            if langue == "ar":
                return (
                    f"يوجد {total} فاتورة: {paid} مؤداة و{unpaid} غير مؤداة. "
                    f"مبلغ غير المؤداة: {float(amount):.2f}."
                )
            return (
                f"Il y a {total} facture(s) : {paid} payée(s) et "
                f"{unpaid} impayée(s). Montant impayé : {float(amount):.2f}."
            )
        finally:
            pool.putconn(conn)

    if any(k in m for k in [
        "comptabil", "accounting", "balance", "solde", "achat",
        "achats", "account", "محاسب", "مشتريات", "رصيد",
    ]):
        if not _has_permission(user, "comptabilite"):
            return _denied(langue, "comptabilite")

        pool = _pool(user)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN statut='payee'
                                          THEN montant_total ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN statut='impayee'
                                          THEN montant_total ELSE 0 END), 0)
                    FROM facture
                    """
                )
                paid, unpaid = cur.fetchone()

                cur.execute(
                    """
                    SELECT COALESCE(SUM(montant_total), 0)
                    FROM achat WHERE statut <> 'annulee'
                    """
                )
                purchases = cur.fetchone()[0]

            return (
                f"Synthèse comptable : factures payées {float(paid):.2f}, "
                f"factures impayées {float(unpaid):.2f}, "
                f"achats {float(purchases):.2f}, "
                f"solde commercial {float(paid-purchases):.2f}."
            )
        finally:
            pool.putconn(conn)

    return None


def _period_clause(message):
    """Retourne une condition SQL pour les périodes courantes."""
    m = message.lower()

    if (
        "ce mois" in m
        or "ce mois-ci" in m
        or "this month" in m
        or "هذا الشهر" in m
    ):
        return (
            "date_commande >= date_trunc('month', CURRENT_DATE) "
            "AND date_commande < date_trunc('month', CURRENT_DATE) "
            "+ INTERVAL '1 month'"
        )

    if "aujourd" in m or "today" in m or "اليوم" in m:
        return (
            "date_commande >= CURRENT_DATE "
            "AND date_commande < CURRENT_DATE + INTERVAL '1 day'"
        )

    return "TRUE"


def _normalize_analytics_text(message):
    """Normalise les variations de texte pour les requêtes analytiques."""
    import unicodedata

    text = (message or "").lower().strip().replace("’", "'")
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _analytics_answer(message, langue, user):
    """Répond aux questions analytiques commerciales en lecture seule."""
    m = _normalize_analytics_text(message)

    sales_words = [
        "vente", "ventes", "chiffre d'affaires", "commandes",
        "sales", "revenue", "orders", "mبيعات", "المبيعات",
        "رقم المعاملات", "طلبات",
    ]
    top_product_words = [
        "produit le plus vendu", "produits les plus vendus",
        "best seller", "best-seller", "top produit", "top products",
        "most sold", "المنتجات الأكثر مبيعا", "أكثر المنتجات مبيعا",
    ]
    top_client_words = [
        "client le plus actif", "clients les plus actifs",
        "meilleur client", "meilleurs clients", "top client", "top clients",
        "best customer", "best customers", "most valuable customer",
        "العملاء الأكثر نشاطا", "أفضل العملاء",
    ]
    unpaid_words = [
        "factures impayées", "facture impayée", "impayé", "impayées",
        "unpaid invoice", "unpaid invoices", "factures non payées",
        "الفواتير غير المؤداة", "فاتورة غير مؤداة",
    ]
    summary_words = [
        "synthese des ventes", "synthese de ventes",
        "synthese des vente", "synthese de vente",
        "resume des ventes", "resume des vente", "resume commercial",
        "synthese commerciale", "sales summary", "commercial summary",
        "sales overview", "overview of sales", "ملخص المبيعات",
        "ملخص المبيعات التجارية", "ملخص تجاري",
    ]

    wants_summary = any(w in m for w in summary_words)
    wants_top_product = any(w in m for w in top_product_words)
    wants_top_client = any(w in m for w in top_client_words)
    wants_unpaid = any(w in m for w in unpaid_words)
    wants_sales = any(w in m for w in sales_words)

    if not (
        wants_summary or wants_top_product or wants_top_client
        or wants_unpaid or wants_sales
    ):
        return None

    pool = _pool(user)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if wants_unpaid and not wants_summary:
                if not _has_permission(user, "facturation", "consulter"):
                    return _denied(langue, "facturation", "consulter")

                cur.execute(
                    """
                    SELECT COUNT(*), COALESCE(SUM(montant_total), 0)
                    FROM facture WHERE statut='impayee'
                    """
                )
                count, amount = cur.fetchone()

                if langue == "en":
                    return (
                        f"There are {count} unpaid invoice(s), for a total "
                        f"of {float(amount):.2f}."
                    )
                if langue == "ar":
                    return (
                        f"يوجد {count} فاتورة غير مؤداة، بمبلغ إجمالي "
                        f"قدره {float(amount):.2f}."
                    )
                return (
                    f"Il y a {count} facture(s) impayée(s), pour un montant "
                    f"total de {float(amount):.2f}."
                )

            if wants_top_product:
                if not _has_permission(user, "ventes", "consulter"):
                    return _denied(langue, "ventes", "consulter")

                clause = _period_clause(m)
                cur.execute(
                    f"""
                    SELECT p.nom,
                           COALESCE(SUM(lc.quantite), 0) AS quantite,
                           COALESCE(SUM(lc.quantite * lc.prix_unitaire), 0) AS ca
                    FROM ligne_commande lc
                    JOIN commande c ON c.id=lc.commande_id
                    JOIN produit p ON p.id=lc.produit_id
                    WHERE c.statut <> 'annulee' AND {clause}
                    GROUP BY p.id, p.nom
                    ORDER BY quantite DESC, ca DESC
                    LIMIT 5
                    """
                )
                rows = cur.fetchall()

                if not rows:
                    return (
                        "Aucune vente de produit trouvée."
                        if langue == "fr"
                        else "No product sales found."
                        if langue == "en"
                        else "لم يتم العثور على مبيعات للمنتجات."
                    )

                if langue == "en":
                    return "Top products by quantity sold:\n" + "\n".join(
                        f"- {n}: {q} unit(s), {float(ca):.2f}"
                        for n, q, ca in rows
                    )
                if langue == "ar":
                    return "أكثر المنتجات مبيعاً حسب الكمية:\n" + "\n".join(
                        f"- {n}: {q} وحدة، {float(ca):.2f}"
                        for n, q, ca in rows
                    )
                return "Produits les plus vendus par quantité :\n" + "\n".join(
                    f"- {n} : {q} unité(s), {float(ca):.2f}"
                    for n, q, ca in rows
                )

            if wants_top_client:
                if not _has_permission(user, "ventes", "consulter"):
                    return _denied(langue, "ventes", "consulter")

                clause = _period_clause(m)
                cur.execute(
                    f"""
                    SELECT cl.nom, COUNT(c.id) AS nb_commandes,
                           COALESCE(SUM(c.montant_total), 0) AS ca
                    FROM commande c
                    JOIN client cl ON cl.id=c.client_id
                    WHERE c.statut <> 'annulee' AND {clause}
                    GROUP BY cl.id, cl.nom
                    ORDER BY ca DESC
                    LIMIT 5
                    """
                )
                rows = cur.fetchall()

                if not rows:
                    return (
                        "Aucune commande trouvée."
                        if langue == "fr"
                        else "No orders found."
                        if langue == "en"
                        else "لم يتم العثور على طلبات."
                    )

                if langue == "en":
                    return "Top customers by revenue:\n" + "\n".join(
                        f"- {n}: {nb} order(s), {float(ca):.2f}"
                        for n, nb, ca in rows
                    )
                if langue == "ar":
                    return "أفضل العملاء حسب رقم المعاملات:\n" + "\n".join(
                        f"- {n}: {nb} طلب، {float(ca):.2f}"
                        for n, nb, ca in rows
                    )
                return "Top clients par chiffre d'affaires :\n" + "\n".join(
                    f"- {n} : {nb} commande(s), {float(ca):.2f}"
                    for n, nb, ca in rows
                )

            if wants_sales or wants_summary:
                if not _has_permission(user, "ventes", "consulter"):
                    return _denied(langue, "ventes", "consulter")

                clause = _period_clause(m)
                cur.execute(
                    f"""
                    SELECT COUNT(*), COALESCE(SUM(montant_total), 0)
                    FROM commande
                    WHERE statut <> 'annulee' AND {clause}
                    """
                )
                nb_commandes, ca = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT COUNT(*), COALESCE(SUM(montant_total), 0)
                    FROM commande
                    WHERE statut='confirmee' AND {clause}
                    """
                )
                nb_conf, ca_conf = cur.fetchone()

                ca = float(ca or 0)
                ca_conf = float(ca_conf or 0)

                if langue == "en":
                    return (
                        "Sales summary\n"
                        f"- Number of orders: {nb_commandes}\n"
                        f"- Total revenue: {ca:.2f}\n"
                        f"- Confirmed orders: {nb_conf}\n"
                        f"- Confirmed-order revenue: {ca_conf:.2f}"
                    )
                if langue == "ar":
                    return (
                        "ملخص المبيعات\n"
                        f"- عدد الطلبات: {nb_commandes}\n"
                        f"- رقم المعاملات الإجمالي: {ca:.2f}\n"
                        f"- عدد الطلبات المؤكدة: {nb_conf}\n"
                        f"- مبلغ الطلبات المؤكدة: {ca_conf:.2f}"
                    )
                return (
                    "Synthèse des ventes\n"
                    f"- Nombre de commandes : {nb_commandes}\n"
                    f"- Chiffre d'affaires : {ca:.2f}\n"
                    f"- Nombre de commandes confirmées : {nb_conf}\n"
                    f"- Montant des commandes confirmées : {ca_conf:.2f}"
                )
    finally:
        pool.putconn(conn)


def _is_documentary_question(message):
    """Détecte les questions qui nécessitent une information documentaire interne."""
    import unicodedata

    def _norm(valeur):
        valeur = (valeur or "").lower().replace("’", "'").replace("'", " ")
        valeur = "".join(
            char for char in unicodedata.normalize("NFKD", valeur)
            if not unicodedata.combining(char)
        )
        return " ".join(valeur.split())

    text = _norm(message)

    document_terms = (
        # Français
        "siege social", "adresse du siege", "adresse de l'entreprise",
        "adresse de la societe", "coordonnees de l'entreprise",
        "histoire de l'entreprise", "politique de l'entreprise",
        "nom de l'entreprise", "nom de la societe", "nom de la compagnie",
        "code de validation", "delai de livraison",
        "procedure interne", "procedures internes",
        "reglement interieur", "conditions de travail",
        "conges", "horaires de travail", "document interne",
        "selon le document", "d'apres le document",
        "dans les documents", "dans la documentation",
        "que dit le document", "quelle est la politique",
        # English
        "headquarters", "company address", "company policy", "company name",
        "internal procedure", "internal procedures",
        "according to the document", "in the company documents",
        "working hours", "leave policy",
        # العربية
        "المقر الرئيسي", "عنوان الشركة", "عنوان المؤسسة", "اسم الشركة", "اسم المؤسسة",
        "سياسة الشركة", "الإجراءات الداخلية", "الوثائق الداخلية",
        "حسب الوثيقة", "حسب المستند", "ساعات العمل",
    )

    return any(_norm(term) in text for term in document_terms)


def _document_not_found(langue):
    """Réponse explicite lorsque les documents ne permettent pas de répondre."""
    if langue == "en":
        return (
            "I couldn't find this information in the available company documents. "
            "I don't want to guess. Please upload the relevant document or "
            "provide a source containing this information."
        )

    if langue == "ar":
        return (
            "لم أجد هذه المعلومة في وثائق الشركة المتاحة، ولا أريد تخمين الإجابة. "
            "يرجى رفع الوثيقة المناسبة أو توفير مصدر يحتوي على هذه المعلومة."
        )

    return (
        "Je n’ai pas trouvé cette information dans les documents disponibles "
        "de l’entreprise. Je préfère ne pas inventer de réponse. "
        "Veuillez importer le document concerné ou fournir une source "
        "contenant cette information."
    )


def _guide(lang, module):
    nom = MODULES.get(module, module)

    if lang == "en":
        return (
            f"You are currently in {nom}. I can consult ERP data, create "
            "records, search clients or suppliers, and guide you through "
            "modifications, subject to your permissions."
        )
    if lang == "ar":
        return (
            f"أنت الآن في وحدة {nom}. يمكنني الاطلاع على بيانات ERP، "
            "إنشاء السجلات، البحث عن العملاء أو الموردين وإرشادك في "
            "التعديلات، حسب صلاحياتك."
        )
    return (
        f"Vous êtes actuellement dans {nom}. Je peux consulter les données "
        "ERP, créer des enregistrements, rechercher des clients ou "
        "fournisseurs et vous guider dans les modifications, selon vos permissions."
    )


def _new_client_question(lang, nom):
    if lang == "en":
        return f'The customer "{nom}" does not exist. Do you want to create it? (yes/no)'
    if lang == "ar":
        return (
            f"العميل «{nom}» غير موجود. هل تريد إنشاءه؟ (نعم/لا)"
        )
    return f"Le client « {nom} » n'existe pas. Voulez-vous le créer ? (oui/non)"


def _new_client_created(lang, nom):
    if lang == "en":
        return f'Customer "{nom}" created and selected.'
    if lang == "ar":
        return f"تم إنشاء العميل «{nom}» واختياره."
    return f"Le client « {nom} » a été créé et sélectionné."


def _est_conversation(message):
    """Vrai si le message est de la conversation courante (salutation, remerciement,
    refus poli, « ok »…) et non une recherche d'information. Dans ce cas on ne
    cherche pas dans les documents. En cas de doute ou d'erreur : faux (on cherche)."""
    texte = (message or "").strip()
    if not texte or len(texte) > 60:
        return False
    try:
        from app.services import llm_client
        reponse = llm_client.chat_completion(
            [
                {"role": "system", "content": (
                    "Classe le message de l'utilisateur d'un assistant ERP. "
                    "Réponds par un seul mot : CHAT ou QUESTION. "
                    "CHAT = salutation, remerciement, au revoir, refus poli (« non merci », "
                    "« I don't want anything »), « ok », politesse ou bavardage, dans n'importe quelle langue. "
                    "QUESTION = demande d'information, de définition, de nom, de chiffre, de liste, "
                    "ou simple terme/nom (ex. « CALMS », « Git », « le professeur ») : "
                    "dès qu'il y a un doute, réponds QUESTION."
                )},
                {"role": "user", "content": texte},
            ],
            temperature=0,
        )
    except Exception:
        return False
    return (reponse or "").strip().upper().startswith("CHAT")


def _termes_de_recherche(question):
    """Mots-clés, synonymes et abréviations proposés par le LLM pour élargir la
    recherche (ex. « professeur » -> « pr prof enseignant »). Jamais bloquant :
    en cas d'erreur ou de question très courte, retourne une chaîne vide."""
    if len((question or "").strip()) < 8:
        return ""
    try:
        from app.services import llm_client
        texte = llm_client.chat_completion(
            [
                {"role": "system", "content": (
                    "Tu aides un moteur de recherche dans des documents. Donne 6 à 8 mots-clés, "
                    "synonymes et abréviations utiles pour retrouver la réponse à la question "
                    "(exemple : professeur -> pr prof enseignant). "
                    "Écris-les en français ET dans la langue de la question (les documents sont souvent en français). "
                    "Réponds sur une seule ligne, uniquement les mots séparés par des espaces, sans phrase."
                )},
                {"role": "user", "content": question.strip()[:300]},
            ],
            temperature=0,
        )
    except Exception:
        return ""
    return " ".join((texte or "").replace(",", " ").split())[:200]


def _rechercher_chunks_rag(utilisateur, question, limite=5):
    """Recherche RAG locale, isolée par base entreprise et filtrée par permissions."""
    if utilisateur.get("type") != "interne" or not utilisateur.get("nomBase"):
        return []

    question = (question or "").strip()
    if len(question) < 3:
        return []

    from app.services.rag_embeddings import (
        embed_texts,
        cosine_similarity,
        MODEL_NAME,
    )

    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Migration idempotente pour les bases déjà provisionnées.
            cur.execute(
                "ALTER TABLE assistant_document_chunk "
                "ADD COLUMN IF NOT EXISTS embedding JSONB"
            )
            cur.execute(
                "ALTER TABLE assistant_document_chunk "
                "ADD COLUMN IF NOT EXISTS embedding_model TEXT"
            )
            cur.execute(
                """
                SELECT id, titre, source, module, contenu, document_id,
                       embedding, embedding_model
                FROM assistant_document_chunk
                WHERE actif = TRUE
                ORDER BY id DESC
                LIMIT 10000
                """
            )
            rows = cur.fetchall()

            a_indexer = [
                row for row in rows
                if not row[6] or row[7] != MODEL_NAME
            ]

            if a_indexer:
                a_indexer = a_indexer[:2000]
                vecteurs = embed_texts([row[4] for row in a_indexer])

                for row, vecteur in zip(a_indexer, vecteurs):
                    import json
                    cur.execute(
                        """
                        UPDATE assistant_document_chunk
                        SET embedding = %s::jsonb, embedding_model = %s
                        WHERE id = %s
                        """,
                        (json.dumps(vecteur), MODEL_NAME, row[0]),
                    )

                conn.commit()

                vecteurs_par_id = {
                    row[0]: vecteur
                    for row, vecteur in zip(a_indexer, vecteurs)
                }
                rows = [
                    tuple(list(row[:6]) + [
                        vecteurs_par_id[row[0]], MODEL_NAME
                    ])
                    if row[0] in vecteurs_par_id
                    else row
                    for row in rows
                ]

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

    termes_etendus = _termes_de_recherche(question)
    query_vector = embed_texts(
        [f"{question} {termes_etendus}".strip()], query=True
    )[0]
    autorise = {}
    scored = []
    proches = []  # passages un peu moins proches : servent à compléter si peu de résultats

    # Recherche hybride : similarité sémantique + correspondance lexicale.
    # La partie lexicale aide à privilégier les passages contenant les termes
    # précis de la question (codes, noms, délais), sans abandonner les synonymes.
    import re
    import unicodedata

    def _normaliser_termes(value):
        value = (value or "").lower().replace("’", "'").replace("_", " ")
        value = "".join(
            c for c in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(c)
        )
        return set(re.findall(r"[\w-]{2,}", value, flags=re.UNICODE))

    question_terms = _normaliser_termes(question)
    stop_words = {
        "quel", "quelle", "quels", "quelles", "comment", "pourquoi",
        "est", "sont", "les", "des", "une", "un", "dans", "pour",
        "avec", "sur", "par", "que", "qui", "quoi", "the", "what",
        "which", "where", "when", "does", "this", "that", "from",
        "and", "for", "are", "was", "les", "der", "die", "und",
    }
    question_terms -= stop_words
    termes_etendus_set = _normaliser_termes(termes_etendus) - stop_words

    # Mots trop répandus (ex. « Pr. » dans l'en-tête de toutes les pages d'un PDF) :
    # ils ne distinguent aucun passage, on les écarte des mots-clés étendus.
    termes_par_chunk = {}
    if termes_etendus_set:
        for row in rows:
            termes_par_chunk[row[0]] = _normaliser_termes(
                " ".join([str(row[1] or ""), str(row[4] or "")])
            )
        total_chunks = max(1, len(termes_par_chunk))
        termes_etendus_set = {
            terme for terme in termes_etendus_set
            if sum(1 for termes in termes_par_chunk.values() if terme in termes) / total_chunks <= 0.3
        }

    for (
        chunk_id, titre, source, module, contenu,
        document_id, embedding, embedding_model,
    ) in rows:
        if not embedding or embedding_model != MODEL_NAME:
            continue

        if isinstance(embedding, str):
            try:
                import json
                embedding = json.loads(embedding)
            except (ValueError, TypeError):
                continue

        semantic_score = cosine_similarity(query_vector, embedding)
        chunk_terms = termes_par_chunk.get(chunk_id) or _normaliser_termes(" ".join([
            str(titre or ""), str(contenu or "")
        ]))
        overlap = len(question_terms & chunk_terms) / max(1, len(question_terms))
        # Un synonyme ou une abréviation proposé par le LLM présent dans le passage
        # compte comme une correspondance lexicale partielle.
        if termes_etendus_set & chunk_terms:
            overlap = max(overlap, 0.25)
        # La similarité sémantique reste majoritaire ; le lexical sert au reranking.
        combined_score = (0.78 * semantic_score) + (0.22 * overlap)
        # Un passage doit avoir une similarité minimale ou une forte correspondance
        # lexicale. Le seuil combiné évite d'afficher systématiquement 5 résultats.
        if semantic_score >= 0.42 or (overlap >= 0.5 and semantic_score >= 0.28):
            scored.append((
                combined_score, semantic_score, overlap, chunk_id,
                titre, source, module, contenu, document_id,
            ))
        elif semantic_score >= 0.32:
            proches.append((
                combined_score, semantic_score, overlap, chunk_id,
                titre, source, module, contenu, document_id,
            ))

    scored.sort(key=lambda item: (item[0], item[1], item[3]), reverse=True)
    n_surs = len(scored)
    # Peu de passages sûrs : on ajoute quelques passages proches. Le LLM écarte
    # ceux qui ne répondent pas (marqueur NON_TROUVE si aucun ne convient).
    if len(scored) < 3 and len(question.strip()) >= 8:
        proches.sort(key=lambda item: (item[0], item[1], item[3]), reverse=True)
        scored = scored + proches[: 4 - len(scored)]
    result = []
    par_document = {}

    for score, semantic_score, lexical_score, chunk_id, titre, source, module, contenu, document_id in scored:
        module = module or "documents"

        if module not in MODULES and module != "documents":
            continue

        # Les documents sans module métier dédié sont consultables par un
        # collaborateur interne autorisé à utiliser l'assistant documentaire.
        if module not in autorise:
            if module == "documents":
                autorise[module] = utilisateur.get("type") == "interne"
            else:
                autorise[module] = _has_permission(
                    utilisateur, module, "consulter"
                )

        if not autorise[module]:
            continue

        # Au plus 2 passages par document : évite qu'un seul document occupe
        # toutes les places et masque les autres documents pertinents.
        if par_document.get(document_id, 0) >= 2:
            continue
        par_document[document_id] = par_document.get(document_id, 0) + 1

        # Les sources visibles et le contexte LLM restent courts : le document
        # complet reste stocké et n'est jamais renvoyé comme réponse.
        excerpt = (contenu or "").strip()
        if len(excerpt) > 280:
            excerpt = excerpt[:280].rsplit(" ", 1)[0] + "…"

        result.append({
            "id": chunk_id,
            "documentId": document_id,
            "title": titre or "Document sans titre",
            "source": source or "Document interne",
            "module": module,
            "excerpt": excerpt,
            "context": (contenu or "").strip()[:1200],
            "score": round(float(score), 4),
            "semanticScore": round(float(semantic_score), 4),
            "lexicalScore": round(float(lexical_score), 4),
        })

        if len(result) >= limite:
            break

    # Début de document : la page de titre porte souvent l'auteur, le professeur,
    # le titre ou la date, mais ressemble rarement à la question posée. On ajoute donc
    # le premier passage des documents les mieux classés (2 au maximum).
    if result:
        premiers = {}
        for row in rows:
            if row[5] is not None and (row[5] not in premiers or row[0] < premiers[row[5]][0]):
                premiers[row[5]] = row
        deja = {item["id"] for item in result}
        ajoutes = 0
        for item in list(result):
            if ajoutes >= 2:
                break
            row = premiers.get(item["documentId"])
            if not row or row[0] in deja:
                continue
            module_p = row[3] or "documents"
            if module_p not in MODULES and module_p != "documents":
                continue
            if module_p not in autorise:
                if module_p == "documents":
                    autorise[module_p] = utilisateur.get("type") == "interne"
                else:
                    autorise[module_p] = _has_permission(utilisateur, module_p, "consulter")
            if not autorise[module_p]:
                continue
            contenu_p = (row[4] or "").strip()
            extrait_p = contenu_p
            if len(extrait_p) > 280:
                extrait_p = extrait_p[:280].rsplit(" ", 1)[0] + "…"
            result.append({
                "id": row[0],
                "documentId": row[5],
                "title": row[1] or "Document sans titre",
                "source": row[2] or "Document interne",
                "module": module_p,
                "excerpt": extrait_p,
                "context": contenu_p[:1200],
                "score": 0.0,
                "semanticScore": 0.0,
                "lexicalScore": 0.0,
            })
            deja.add(row[0])
            ajoutes += 1

    # Diagnostic (activé avec RAG_DEBUG=1 dans le .env) : permet de voir pourquoi
    # un passage est retrouvé ou non. Aucun effet sinon.
    import os
    if os.getenv("RAG_DEBUG") == "1":
        import logging
        journal = logging.getLogger("erp.rag.debug")
        journal.warning(
            "RAG question=%r termes_etendus=%r passages_surs=%d retenus=%d",
            question, termes_etendus, n_surs, len(result),
        )
        for rang, item in enumerate(result, 1):
            journal.warning(
                "RAG  #%d score=%.3f sem=%.3f lex=%.2f | %s | %s",
                rang, item["score"], item["semanticScore"], item["lexicalScore"],
                item["source"], (item.get("context") or "")[:90].replace("\n", " "),
            )

    return result


def _reponse_rag(sources, langue):
    from app.services.rag_response import reponse_rag_concise
    return reponse_rag_concise(sources, langue)


@router.post("/chat")
def chat(
    payload: AssistantMessage,
    utilisateur=Depends(utilisateur_connecte),
):
    if not utilisateur.get("nomBase") or utilisateur.get("type") == "externe":
        raise HTTPException(
            403,
            "Assistant réservé aux collaborateurs de l'entreprise.",
        )

    m = payload.message.lower().strip()
    state = payload.state.model_copy(deep=True)
    prompts = _prompts(payload.langue)

    # Ne pas reclassifier une réponse de suivi si un workflow est actif.
    understanding = (
        _understand_message(payload.message, payload.langue)
        if not state.operation
        else {"intent": None, "entities": {}}
    )
    intent = understanding.get("intent")
    entities = understanding.get("entities") or {}

    if intent:
        if intent == "create_commande":
            if not _has_permission(utilisateur, "ventes", "creer"):
                return {
                    "reply": _denied(payload.langue, "ventes", "creer"),
                    "state": AssistantState().model_dump(),
                }

            if not _has_permission(utilisateur, "clients", "consulter"):
                return {
                    "reply": _denied(payload.langue, "clients", "consulter"),
                    "state": AssistantState().model_dump(),
                }

            state = AssistantState(
                operation="create_commande",
                step="client",
                data={},
            )
            client_name = entities.get("client_name")

            if client_name:
                rows = _find_entity(utilisateur, "client", client_name)
                exact = [
                    row for row in rows
                    if str(row.get("nom", "")).strip().casefold()
                    == client_name.strip().casefold()
                ]
                selected = (
                    exact[0]
                    if len(exact) == 1
                    else rows[0]
                    if len(rows) == 1
                    else None
                )

                if selected:
                    state.data = {
                        "client_id": selected["id"],
                        "client_nom": selected["nom"],
                        "lines": [],
                    }
                    state.step = "product"

                    if payload.langue == "fr":
                        reply = (
                            f"Client sélectionné : {selected['nom']}.\n\n"
                            f"{prompts['order_product']}"
                        )
                    elif payload.langue == "en":
                        reply = (
                            f"Customer selected: {selected['nom']}.\n\n"
                            f"{prompts['order_product']}"
                        )
                    else:
                        reply = (
                            f"تم اختيار العميل: {selected['nom']}.\n\n"
                            f"{prompts['order_product']}"
                        )

                    return {"reply": reply, "state": state.model_dump()}

            return {
                "reply": prompts["order_client"],
                "state": state.model_dump(),
            }

        # Compatibilité des noms de workflow fournisseur.
        parts = intent.split("_", 1)
        entity = parts[1] if len(parts) > 1 else ""
        if entity == "supplier":
            entity = "fournisseur"

        if entity not in {"client", "fournisseur"}:
            entity = None

        if entity:
            module, _ = _entity_meta(entity)
            action = (
                "creer"
                if intent.startswith("create")
                else "consulter"
                if intent.startswith("search")
                else "modifier"
            )

            if not _has_permission(utilisateur, module, action):
                return {
                    "reply": _denied(payload.langue, module, action),
                    "state": AssistantState().model_dump(),
                }

            if intent.startswith("create"):
                initial_data = {}
                initial_name = (
                    entities.get("client_name")
                    if entity == "client"
                    else entities.get("supplier_name")
                )

                if initial_name:
                    initial_data["nom"] = initial_name
                    state = AssistantState(
                        operation=f"create_{entity}",
                        step="email",
                        data=initial_data,
                    )
                    return {
                        "reply": prompts["email"],
                        "state": state.model_dump(),
                    }

                state = AssistantState(
                    operation=f"create_{entity}",
                    step="nom",
                    data=initial_data,
                )
                return {
                    "reply": prompts["nom"],
                    "state": state.model_dump(),
                }

            if intent.startswith("search"):
                query = m
                for w in [
                    "chercher", "rechercher", "recherche", "trouver",
                    "cherche", "find", "search", "look for", "client",
                    "clients", "customer", "customers", "fournisseur",
                    "fournisseurs", "supplier", "suppliers", "بحث",
                    "ابحث", "البحث", "عميل", "مورد",
                ]:
                    query = query.replace(w, " ")

                rows = _find_entity(
                    utilisateur, entity, query.strip()
                ) if query.strip() else []

                return {
                    "reply": (
                        _format_search(rows, entity, payload.langue)
                        if rows
                        else prompts["search"]
                    ),
                    "state": AssistantState().model_dump(),
                }

            state = AssistantState(
                operation=f"edit_{entity}",
                step="search",
                data={},
            )
            return {
                "reply": prompts["search"],
                "state": state.model_dump(),
            }

    op = state.operation
    step = state.step
    data = state.data

    if op == "create_commande":
        if step == "client":
            rows = _find_entity(utilisateur, "client", payload.message)

            if len(rows) == 0 and payload.message.strip():
                if not _has_permission(utilisateur, "clients", "creer"):
                    return {
                        "reply": (
                            _format_search(rows, "client", payload.langue)
                            + "\n\n" + prompts["order_client"]
                        ),
                        "state": state.model_dump(),
                    }

                data["new_client_nom"] = payload.message.strip()
                state.step = "confirm_new_client"
                state.data = data
                return {
                    "reply": _new_client_question(
                        payload.langue, data["new_client_nom"]
                    ),
                    "state": state.model_dump(),
                }

            if len(rows) != 1:
                return {
                    "reply": (
                        _format_search(rows, "client", payload.langue)
                        + "\n\n" + prompts["order_client"]
                    ),
                    "state": state.model_dump(),
                }

            data["client_id"] = rows[0]["id"]
            data["client_nom"] = rows[0]["nom"]
            data["lines"] = []
            state.step = "product"
            reply = (
                f"Client sélectionné : {rows[0]['nom']}.\n\n"
                f"{prompts['order_product']}"
            )

        elif step == "confirm_new_client":
            if _is_yes(m):
                nom = data.get("new_client_nom", "")
                try:
                    created = _create_entity(
                        utilisateur, "client", {"nom": nom}
                    )
                except HTTPException as e:
                    state.step = "client"
                    reply = str(e.detail) + "\n\n" + prompts["order_client"]
                else:
                    data["client_id"] = created["id"]
                    data["client_nom"] = created["nom"]
                    data["lines"] = []
                    data.pop("new_client_nom", None)
                    state.step = "product"
                    reply = (
                        _new_client_created(payload.langue, created["nom"])
                        + "\n\n" + prompts["order_product"]
                    )
            elif _is_no(m):
                data.pop("new_client_nom", None)
                state.step = "client"
                reply = prompts["order_client"]
            else:
                reply = _new_client_question(
                    payload.langue, data.get("new_client_nom", "")
                )

        elif step == "product":
            rows = _search_products(utilisateur, payload.message)
            if len(rows) != 1:
                return {
                    "reply": (
                        _format_products(rows, payload.langue)
                        + "\n\n" + prompts["order_product"]
                    ),
                    "state": state.model_dump(),
                }

            data["current_product"] = {
                "id": rows[0]["id"],
                "nom": rows[0]["nom"],
                "prix": rows[0]["prix_unitaire"],
                "stock": rows[0]["stock_actuel"],
            }
            state.step = "quantity"
            reply = (
                f"Produit sélectionné : {rows[0]['nom']} | "
                f"Prix unitaire : {rows[0]['prix_unitaire']:.2f} | "
                f"Stock disponible : {rows[0]['stock_actuel']}.\n\n"
                f"{prompts['order_qty']}"
            )

        elif step == "quantity":
            try:
                qty = int(payload.message.strip())
            except ValueError:
                qty = 0

            cp = data.get("current_product", {})
            if qty <= 0:
                reply = prompts["order_qty"]
            elif qty > cp.get("stock", 0):
                reply = (
                    f"Stock insuffisant : {cp.get('stock', 0)} disponible(s).\n\n"
                    f"{prompts['order_qty']}"
                )
            else:
                data["lines"].append({
                    "produit_id": cp["id"],
                    "nom": cp["nom"],
                    "quantite": qty,
                    "prix": cp["prix"],
                })
                data.pop("current_product", None)
                state.step = "more"
                reply = prompts["order_more"]

        elif step == "more":
            if _is_yes(m):
                state.step = "product"
                reply = prompts["order_product"]
            elif _is_no(m):
                total = sum(
                    Decimal(str(x["prix"])) * x["quantite"]
                    for x in data.get("lines", [])
                ).quantize(Decimal("0.01"))
                data["total"] = float(total)
                state.step = "confirmation"
                lines = "\n".join(
                    f"- {x['nom']} × {x['quantite']} = "
                    f"{Decimal(str(x['prix'])) * x['quantite']:.2f}"
                    for x in data["lines"]
                )
                reply = (
                    "Récapitulatif de la commande\n"
                    f"Client : {data['client_nom']}\n{lines}\n"
                    f"Total : {total:.2f}\n\n{prompts['order_confirm']}"
                )
            else:
                reply = prompts["order_more"]

        elif step == "confirmation":
            if _is_yes(m):
                result = _create_order(
                    utilisateur, data["client_id"], data["lines"]
                )
                data["commande_id"] = result["id"]
                data["numero"] = result["numero"]
                state.step = "facturation"
                reply = (
                    f"Commande {result['numero']} créée avec succès. "
                    f"Total : {result['total']:.2f}.\n\n{prompts['invoice']}"
                )
            elif _is_no(m):
                state = AssistantState()
                reply = (
                    "Operation cancelled."
                    if payload.langue == "en"
                    else "تم إلغاء العملية."
                    if payload.langue == "ar"
                    else "Opération annulée."
                )
            else:
                reply = prompts["order_confirm"]

        elif step == "facturation":
            if _is_yes(m):
                if not _has_permission(utilisateur, "facturation", "creer"):
                    state = AssistantState()
                    reply = _denied(
                        payload.langue, "facturation", "creer"
                    )
                else:
                    inv = _create_invoice(utilisateur, data["commande_id"])
                    state = AssistantState()
                    reply = f"Facture {inv['numero']} créée avec succès."
            elif _is_no(m):
                state = AssistantState()
                reply = (
                    "Commande conservée sans facturation."
                    if payload.langue == "fr"
                    else "Order kept without invoicing."
                    if payload.langue == "en"
                    else "تم الاحتفاظ بالطلب بدون فوترة."
                )
            else:
                reply = prompts["invoice"]

        else:
            state = AssistantState()
            reply = _guide(payload.langue, payload.module)

        state.data = data
        return {"reply": reply, "state": state.model_dump()}

    # Noms canoniques des opérations fournisseur.
    if op in {
        "create_client", "create_supplier", "create_fournisseur",
    }:
        entity = "client" if op == "create_client" else "fournisseur"

        if step == "nom":
            data["nom"] = payload.message.strip()
            state.step = "email"
            reply = prompts["email"]
        elif step == "email":
            data["email"] = "" if _is_skip(m) else payload.message.strip()
            state.step = "telephone"
            reply = prompts["telephone"]
        elif step == "telephone":
            data["telephone"] = "" if _is_skip(m) else payload.message.strip()
            state.step = "adresse"
            reply = prompts["adresse"]
        elif step == "adresse":
            data["adresse"] = "" if _is_skip(m) else payload.message.strip()
            state.step = "confirmation"
            reply = _summary(entity, data, payload.langue) + "\n\n" + prompts["confirm"]
        elif step == "confirmation":
            if _is_yes(m):
                result = _create_entity(utilisateur, entity, data)
                state = AssistantState()
                label = _label(entity, payload.langue)
                reply = (
                    f"{label.capitalize()} created successfully: {result['nom']}."
                    if payload.langue == "en"
                    else f"تم إنشاء {label} بنجاح: {result['nom']}."
                    if payload.langue == "ar"
                    else f"Le {label} « {result['nom']} » a été créé avec succès."
                )
            elif _is_no(m):
                state = AssistantState()
                reply = (
                    "Operation cancelled."
                    if payload.langue == "en"
                    else "تم إلغاء العملية."
                    if payload.langue == "ar"
                    else "Opération annulée."
                )
            else:
                reply = prompts["confirm"]
        else:
            state = AssistantState()
            reply = _guide(payload.langue, payload.module)

        state.data = data
        return {"reply": reply, "state": state.model_dump()}

    if op in {
        "edit_client", "edit_supplier", "edit_fournisseur",
    }:
        entity = "client" if op == "edit_client" else "fournisseur"

        if step == "search":
            rows = _find_entity(utilisateur, entity, payload.message)

            if not rows:
                return {
                    "reply": (
                        "No matching record was found. Please give another name."
                        if payload.langue == "en"
                        else "لم يتم العثور على سجل مطابق. أعطني اسماً آخر."
                        if payload.langue == "ar"
                        else "Aucun enregistrement trouvé. Donnez un autre nom."
                    ),
                    "state": state.model_dump(),
                }

            if len(rows) > 1:
                return {
                    "reply": _format_search(rows, entity, payload.langue)
                    + "\n\n" + prompts["search"],
                    "state": state.model_dump(),
                }

            state.step = "field"
            state.data = {
                "id": rows[0]["id"],
                "nom": rows[0]["nom"],
                "email": rows[0].get("email"),
                "telephone": rows[0].get("telephone"),
                "adresse": rows[0].get("adresse"),
            }
            return {
                "reply": _format_search(rows, entity, payload.langue)
                + "\n\n" + prompts["field"],
                "state": state.model_dump(),
            }

        if step == "field":
            aliases = {
                "nom": "nom", "name": "nom", "اسم": "nom",
                "email": "email", "e-mail": "email", "البريد": "email",
                "telephone": "telephone", "téléphone": "telephone",
                "phone": "telephone", "هاتف": "telephone",
                "adresse": "adresse", "address": "adresse", "العنوان": "adresse",
            }
            field = next((v for k, v in aliases.items() if k in m), None)
            if not field:
                return {"reply": prompts["field"], "state": state.model_dump()}

            state.data["field"] = field
            state.step = "value"
            return {"reply": prompts["value"], "state": state.model_dump()}

        if step == "value":
            state.data["value"] = payload.message.strip()
            state.step = "confirmation"
            field = state.data["field"]
            old = state.data.get(field) or (
                "non renseigné"
                if payload.langue == "fr"
                else "not provided"
                if payload.langue == "en"
                else "غير محدد"
            )
            label = {
                "fr": "client" if entity == "client" else "fournisseur",
                "en": "customer" if entity == "client" else "supplier",
                "ar": "العميل" if entity == "client" else "المورد",
            }[payload.langue]

            if payload.langue == "fr":
                reply = (
                    f"Modification du {label} « {state.data['nom']} » :\n"
                    f"- {field} : {old} → {state.data['value']}\n\n"
                    f"{prompts['editconfirm']}"
                )
            elif payload.langue == "en":
                reply = (
                    f"Modification for {label} “{state.data['nom']}”:\n"
                    f"- {field}: {old} → {state.data['value']}\n\n"
                    f"{prompts['editconfirm']}"
                )
            else:
                reply = (
                    f"تعديل {label} «{state.data['nom']}»:\n"
                    f"- {field}: {old} ← {state.data['value']}\n\n"
                    f"{prompts['editconfirm']}"
                )

            return {"reply": reply, "state": state.model_dump()}

        if step == "confirmation":
            if _is_yes(m):
                _update_entity(
                    utilisateur,
                    entity,
                    state.data["id"],
                    state.data["field"],
                    state.data["value"],
                )
                state = AssistantState()
                return {
                    "reply": (
                        "Modification completed successfully."
                        if payload.langue == "en"
                        else "تم تعديل السجل بنجاح."
                        if payload.langue == "ar"
                        else "La modification a été enregistrée avec succès."
                    ),
                    "state": state.model_dump(),
                }

            if _is_no(m):
                return {
                    "reply": (
                        "Operation cancelled."
                        if payload.langue == "en"
                        else "تم إلغاء العملية."
                        if payload.langue == "ar"
                        else "Modification annulée."
                    ),
                    "state": AssistantState().model_dump(),
                }

            return {
                "reply": prompts["editconfirm"],
                "state": state.model_dump(),
            }

    # Recherche documentaire locale : aucune clé API n'est requise pour récupérer
    # les passages. La génération de réponse reste facultative.
    sources = []
    answer = None
    rag_error = False

    try:
        # Conversation courante : pas de recherche documentaire (évite de résumer
        # un document en réponse à « merci » ou « non merci »).
        if not _est_conversation(payload.message):
            sources = _rechercher_chunks_rag(utilisateur, payload.message)
    except RuntimeError:
        import logging
        logging.getLogger("erp.rag").exception(
            "Recherche sémantique RAG indisponible"
        )
        rag_error = True

    if rag_error:
        answer = (
            "Le moteur de recherche documentaire local n'est pas prêt. "
            "Vérifiez le modèle d'embeddings dans le backend."
            if payload.langue == "fr"
            else "The local document search engine is not ready. "
                 "Check the backend embedding model."
            if payload.langue == "en"
            else "محرك البحث المحلي في الوثائق غير جاهز. "
                 "تحقق من نموذج التضمين في الخادم."
        )
    elif sources:
        answer = _reponse_rag(sources, payload.langue)

        # La génération peut être indisponible : les extraits et leurs sources
        # restent alors disponibles comme réponse de repli.
        try:
            from app.services.rag_generation import generer_reponse
            reponse_generee = generer_reponse(
                payload.message, sources, payload.langue
            )
            if reponse_generee:
                import re as _re
                # Le modèle écrit parfois le marqueur sans crochets (NON_TROUVE, NON TROUVÉ…).
                # Une étiquette entre crochets en tête de réponse ([MERCI], [MONTRE]…) est
                # aussi un signe que le modèle n'a pas su répondre à partir des passages.
                if (
                    _re.search(r"NON[_ \-]?TROUV", reponse_generee, _re.IGNORECASE)
                    or _re.match(r"\s*\[[A-ZÀ-ÝÉÈ_ ]{2,20}\]", reponse_generee)
                ):
                    # Les passages ne répondent pas à la question : on retire les
                    # sources hors sujet et on laisse la suite (données ERP, puis
                    # réponse générale du LLM : salutation, remerciement, ou
                    # « information non trouvée ») formuler la réponse.
                    sources = []
                    answer = None
                else:
                    answer = reponse_generee
        except Exception:
            import logging
            logging.getLogger("erp.rag").exception(
                "Génération RAG indisponible; conservation des extraits récupérés"
            )

    # Les questions analytiques et les données ERP gardent la priorité
    # sur le message générique, mais ne remplacent pas un résultat RAG.
    if answer is None:
        answer = _analytics_answer(
            payload.message, payload.langue, utilisateur
        )

    if answer is None:
        answer = _answer_data(
            payload.message, payload.langue, utilisateur
        )

    # Ne pas afficher le guide générique lorsqu'une question documentaire
    # n'a pas de réponse dans les documents récupérés.
    # Aucun passage pertinent ni donnée ERP : on laisse le LLM répondre
    # naturellement (salutation, conversation, question hors documents) en lui
    # interdisant d'inventer des informations propres à l'entreprise.
    if answer is None:
        try:
            from app.services.rag_generation import repondre_hors_documents
            answer = repondre_hors_documents(
                payload.message, payload.langue,
                MODULES.get(payload.module, payload.module),
            )
        except Exception:
            import logging
            logging.getLogger("erp.rag").exception(
                "Réponse hors documents indisponible; repli sur les règles fixes"
            )

    # Repli si le LLM est indisponible : comportement précédent.
    if answer is None:
        if _is_documentary_question(payload.message):
            answer = _document_not_found(payload.langue)
        else:
            answer = _guide(payload.langue, payload.module)

    if not answer or not str(answer).strip():
        answer = _guide(payload.langue, payload.module)

    # Le passage complet ne sert qu'au LLM : le navigateur reçoit l'extrait court.
    sources = [
        {cle: valeur for cle, valeur in item.items() if cle != "context"}
        for item in sources
    ]

    return {
        "reply": answer,
        "sources": sources,
        "module": payload.module,
        "langue": payload.langue,
        "state": AssistantState().model_dump(),
    }
