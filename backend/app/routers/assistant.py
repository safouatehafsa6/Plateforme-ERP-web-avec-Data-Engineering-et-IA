from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from decimal import Decimal
from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
MODULES = {"dashboard":"Tableau de bord","ventes":"Ventes","achats":"Achats","fournisseurs":"Fournisseurs","clients":"Clients","stock":"Stock","facturation":"Facturation","comptabilite":"Comptabilité","parametres":"Paramètres","collaborateurs":"Collaborateurs","roles-permissions":"Rôles & Permissions","utilisateurs-externes":"Utilisateurs externes"}

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

def _pool(user): return get_pool_entreprise(user["nomBase"])

def _has_permission(user, module, action="consulter"):
    if user.get("role") == "Admin": return True
    uid = user.get("id")
    if not uid or not user.get("nomBase") or user.get("type") == "externe": return False
    pool = _pool(user); conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM utilisateur u JOIN role_permission rp ON rp.role_id=u.role_id JOIN permission p ON p.id=rp.permission_id WHERE u.id=%s AND u.actif=TRUE AND p.module=%s AND p.action=%s LIMIT 1""", (uid,module,action))
            return cur.fetchone() is not None
    finally: pool.putconn(conn)

def _denied(langue,module,action="consulter"):
    if langue == "en": return f"I cannot perform this operation because your account does not have the required permission ({module}.{action})."
    if langue == "ar": return f"لا يمكنني تنفيذ هذه العملية لأن حسابك لا يملك الصلاحية المطلوبة ({module}.{action})."
    return f"Je ne peux pas effectuer cette opération car votre compte ne possède pas la permission requise ({module}.{action})."

def _entity_meta(entity):
    return ("clients","client") if entity == "client" else ("fournisseurs","fournisseur")

def _create_entity(user, entity, data):
    module, table = _entity_meta(entity)
    if not _has_permission(user,module,"creer"): raise HTTPException(403,_denied("fr",module,"creer"))
    nom=(data.get("nom") or "").strip()
    if not nom: raise HTTPException(422,"Le nom est obligatoire.")
    vals={k:((data.get(k) or "").strip() or None) for k in ("email","telephone","adresse")}
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM {table} WHERE LOWER(nom)=LOWER(%s) LIMIT 1",(nom,))
            if cur.fetchone(): raise HTTPException(409,f"Un {entity} portant ce nom existe déjà.")
            cur.execute(f"INSERT INTO {table} (nom,email,telephone,adresse) VALUES (%s,%s,%s,%s) RETURNING id,nom,email,telephone,adresse",(nom,vals["email"],vals["telephone"],vals["adresse"]))
            row=cur.fetchone(); result=dict(zip([d[0] for d in cur.description],row))
        conn.commit(); return result
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)

def _find_entity(user,entity,query):
    module,table=_entity_meta(entity)
    if not _has_permission(user,module,"consulter"): raise HTTPException(403,_denied("fr",module,"consulter"))
    q=(query or "").strip()
    if not q: return []
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id,nom,email,telephone,adresse FROM {table} WHERE nom ILIKE %s OR COALESCE(email,'') ILIKE %s OR COALESCE(telephone,'') ILIKE %s ORDER BY nom LIMIT 10",(f"%{q}%",f"%{q}%",f"%{q}%"))
            rows=cur.fetchall(); cols=[d[0] for d in cur.description]
            return [dict(zip(cols,[ _fmt(v) for v in row])) for row in rows]
    finally: pool.putconn(conn)

def _update_entity(user,entity,entity_id,field,value):
    module,table=_entity_meta(entity)
    if not _has_permission(user,module,"modifier"): raise HTTPException(403,_denied("fr",module,"modifier"))
    allowed={"nom","email","telephone","adresse"}
    if field not in allowed: raise HTTPException(422,"Champ de modification non autorisé.")
    value=(value or "").strip() or None
    if field=="nom" and not value: raise HTTPException(422,"Le nom est obligatoire.")
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            if field=="nom":
                cur.execute(f"SELECT 1 FROM {table} WHERE LOWER(nom)=LOWER(%s) AND id<>%s LIMIT 1",(value,entity_id))
                if cur.fetchone(): raise HTTPException(409,"Un autre enregistrement porte déjà ce nom.")
            cur.execute(f"UPDATE {table} SET {field}=%s WHERE id=%s RETURNING id,nom,email,telephone,adresse",(value,entity_id))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Enregistrement introuvable.")
            result=dict(zip([d[0] for d in cur.description],row))
        conn.commit(); return result
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)


def _search_products(user, query):
    if not _has_permission(user, "stock", "consulter"):
        raise HTTPException(403, _denied("fr", "stock", "consulter"))
    q=(query or "").strip()
    if not q: return []
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, reference, nom, categorie, prix_unitaire, COALESCE(stock_actuel,0) AS stock_actuel
                           FROM produit WHERE reference ILIKE %s OR nom ILIKE %s
                           ORDER BY nom LIMIT 10""", (f"%{q}%", f"%{q}%"))
            rows=cur.fetchall(); cols=[d[0] for d in cur.description]
            return [dict(zip(cols, [_fmt(v) for v in row])) for row in rows]
    finally: pool.putconn(conn)

def _format_products(rows, lang):
    if not rows:
        return "Aucun produit correspondant n’a été trouvé." if lang=="fr" else "No matching product was found." if lang=="en" else "لم يتم العثور على منتج مطابق."
    lines=[f"- {r['nom']} | Réf: {r['reference']} | Prix: {r['prix_unitaire']:.2f} | Stock: {r['stock_actuel']}" for r in rows]
    if lang=="en": lines=[f"- {r['nom']} | Ref: {r['reference']} | Price: {r['prix_unitaire']:.2f} | Stock: {r['stock_actuel']}" for r in rows]
    if lang=="ar": lines=[f"- {r['nom']} | المرجع: {r['reference']} | السعر: {r['prix_unitaire']:.2f} | المخزون: {r['stock_actuel']}" for r in rows]
    return ("Produits trouvés :\n" if lang=="fr" else "Products found:\n" if lang=="en" else "المنتجات التي تم العثور عليها:\n") + "\n".join(lines)

def _create_order(user, client_id, lines):
    if not _has_permission(user, "ventes", "creer"):
        raise HTTPException(403, _denied("fr", "ventes", "creer"))
    if not _has_permission(user, "stock", "consulter"):
        raise HTTPException(403, _denied("fr", "stock", "consulter"))
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client WHERE id=%s", (client_id,))
            if not cur.fetchone(): raise HTTPException(404, "Client introuvable.")
            total=Decimal("0")
            normalized=[]
            for line in lines:
                cur.execute("SELECT id, nom, prix_unitaire, COALESCE(stock_actuel,0) FROM produit WHERE id=%s", (line["produit_id"],))
                row=cur.fetchone()
                if not row: raise HTTPException(404, "Produit introuvable.")
                if row[3] < line["quantite"]:
                    raise HTTPException(400, f"Stock insuffisant pour {row[1]} : disponible {row[3]}, demandé {line['quantite']}.")
                total += Decimal(str(row[2])) * line["quantite"]
                normalized.append((row[0], line["quantite"], row[2]))
            total=total.quantize(Decimal("0.01"))
            cur.execute("SELECT nextval('seq_commande_numero')")
            numero=f"CMD-{__import__('datetime').datetime.now().year}-{cur.fetchone()[0]:06d}"
            cur.execute("INSERT INTO commande (client_id, statut, montant_total, numero) VALUES (%s,'confirmee',%s,%s) RETURNING id", (client_id,total,numero))
            commande_id=cur.fetchone()[0]
            cur.executemany("INSERT INTO ligne_commande (commande_id, produit_id, quantite, prix_unitaire) VALUES (%s,%s,%s,%s)", [(commande_id,pid,q,pu) for pid,q,pu in normalized])
        conn.commit()
        return {"id":commande_id,"numero":numero,"total":float(total)}
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)

def _create_invoice(user, commande_id):
    if not _has_permission(user, "facturation", "creer"):
        raise HTTPException(403, _denied("fr", "facturation", "creer"))
    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, numero FROM facture WHERE commande_id=%s ORDER BY id LIMIT 1", (commande_id,))
            existing=cur.fetchone()
            if existing: return {"id":existing[0],"numero":existing[1]}
            cur.execute("SELECT montant_total, statut FROM commande WHERE id=%s", (commande_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Commande introuvable.")
            cur.execute("SELECT nextval('seq_facture_numero')")
            numero=f"FAC-{__import__('datetime').datetime.now().year}-{cur.fetchone()[0]:06d}"
            cur.execute("INSERT INTO facture (commande_id, numero, montant_total, statut, code_verification) VALUES (%s,%s,%s,'impayee',encode(gen_random_bytes(24),'hex')) RETURNING id", (commande_id,numero,row[0]))
            fid=cur.fetchone()[0]
            cur.execute("""INSERT INTO ligne_facture (facture_id, produit_id, designation, quantite, prix_unitaire, remise_pct)
                           SELECT %s, lc.produit_id, p.nom, lc.quantite, lc.prix_unitaire, 0
                           FROM ligne_commande lc JOIN produit p ON p.id=lc.produit_id WHERE lc.commande_id=%s""", (fid,commande_id))
        conn.commit(); return {"id":fid,"numero":numero}
    except Exception:
        conn.rollback(); raise
    finally: pool.putconn(conn)

def _is_yes(m): return m.strip().lower() in {"oui","yes","y","ok","d'accord","daccord","confirmer","confirme","نعم","موافق"}
def _is_no(m): return m.strip().lower() in {"non","no","n","annuler","annule","cancel","لا","إلغاء","الغاء"}
def _is_skip(m): return m.strip().lower() in {"passer","skip","aucun","aucune","لا","تخطي","تخطى"}

def _prompts(lang):
    if lang=="en": return {"nom":"What is the name?","email":"What is the email? (optional — type 'skip')","telephone":"What is the phone number? (optional — type 'skip')","adresse":"What is the address? (optional — type 'skip')","confirm":"Please confirm. Do you want me to create it? (yes/no)","search":"What client/supplier name should I search for?","field":"Which field do you want to modify: name, email, phone or address?","value":"What is the new value?","editconfirm":"Please confirm this modification (yes/no).","order_client":"Quel client souhaitez-vous utiliser pour la commande ?","order_product":"Quel produit souhaitez-vous ajouter ?","order_qty":"Quelle quantité souhaitez-vous commander ?","order_more":"Voulez-vous ajouter un autre produit ? (oui/non)","order_confirm":"Voici le récapitulatif de la commande. Voulez-vous confirmer la création ? (oui/non)","invoice":"La commande a été créée. Voulez-vous préparer la facture maintenant ? (oui/non)"}
    if lang=="ar": return {"nom":"ما الاسم؟","email":"ما البريد الإلكتروني؟ (اختياري — اكتب تخطي)","telephone":"ما رقم الهاتف؟ (اختياري — اكتب تخطي)","adresse":"ما العنوان؟ (اختياري — اكتب تخطي)","confirm":"راجع المعلومات. هل تريد إنشاء السجل؟ (نعم/لا)","search":"ما اسم العميل أو المورد الذي تريد البحث عنه؟","field":"ما الحقل الذي تريد تعديله: الاسم أو البريد أو الهاتف أو العنوان؟","value":"ما القيمة الجديدة؟","editconfirm":"هل تؤكد هذا التعديل؟ (نعم/لا)","order_client":"ما العميل الذي تريد إنشاء الطلب له؟","order_product":"ما المنتج الذي تريد إضافته؟","order_qty":"ما الكمية التي تريد طلبها؟","order_more":"هل تريد إضافة منتج آخر؟ (نعم/لا)","order_confirm":"هذا هو ملخص الطلب. هل تريد تأكيد إنشاءه؟ (نعم/لا)","invoice":"تم إنشاء الطلب. هل تريد إعداد الفاتورة الآن؟ (نعم/لا)"}
    return {"nom":"Quel est le nom ?","email":"Quel est l’e-mail ? (facultatif — écrivez « passer »)","telephone":"Quel est le téléphone ? (facultatif — écrivez « passer »)","adresse":"Quelle est l’adresse ? (facultatif — écrivez « passer »)","confirm":"Voici le récapitulatif. Voulez-vous confirmer la création ? (oui/non)","search":"Quel nom de client ou de fournisseur souhaitez-vous rechercher ?","field":"Quel champ souhaitez-vous modifier : nom, e-mail, téléphone ou adresse ?","value":"Quelle est la nouvelle valeur ?","editconfirm":"Confirmez-vous cette modification ? (oui/non)","order_client":"Quel client souhaitez-vous utiliser pour la commande ?","order_product":"Quel produit souhaitez-vous ajouter ?","order_qty":"Quelle quantité souhaitez-vous commander ?","order_more":"Voulez-vous ajouter un autre produit ? (oui/non)","order_confirm":"Voici le récapitulatif de la commande. Voulez-vous confirmer la création ? (oui/non)","invoice":"La commande a été créée. Voulez-vous préparer la facture maintenant ? (oui/non)"}

def _label(entity,lang):
    if lang=="en": return "customer" if entity=="client" else "supplier"
    if lang=="ar": return "العميل" if entity=="client" else "المورد"
    return "client" if entity=="client" else "fournisseur"

def _summary(entity,data,lang):
    label=_label(entity,lang); missing={"fr":"non renseigné","en":"not provided","ar":"غير محدد"}
    def v(k): return data.get(k) or missing[lang]
    if lang=="en": return f"Summary for {label}:\n- Name: {v('nom')}\n- Email: {v('email')}\n- Phone: {v('telephone')}\n- Address: {v('adresse')}"
    if lang=="ar": return f"ملخص {label}:\n- الاسم: {v('nom')}\n- البريد: {v('email')}\n- الهاتف: {v('telephone')}\n- العنوان: {v('adresse')}"
    return f"Récapitulatif du {label} :\n- Nom : {v('nom')}\n- E-mail : {v('email')}\n- Téléphone : {v('telephone')}\n- Adresse : {v('adresse')}"

def _format_search(rows,entity,lang):
    if not rows:
        return {"fr":f"Aucun {entity} correspondant n’a été trouvé.","en":f"No matching {('customer' if entity=='client' else 'supplier')} was found.","ar":f"لم يتم العثور على {('عميل' if entity=='client' else 'مورد')} مطابق."}[lang]
    lines=[]
    for r in rows:
        lines.append(f"- {r['nom']} | {r.get('email') or '-'} | {r.get('telephone') or '-'} | {r.get('adresse') or '-'}")
    if lang=="en": return "Search results:\n"+"\n".join(lines)
    if lang=="ar": return "نتائج البحث:\n"+"\n".join(lines)
    return "Résultats de recherche :\n"+"\n".join(lines)

def _normalize_nlu_text(value):
    """Normalize accents and punctuation for multilingual intent fallback."""
    import re
    import unicodedata
    text=(value or "").lower().replace("’", "'").replace("œ", "oe").replace("æ", "ae")
    text="".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text=re.sub(r"[^\w\s@.+/-]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _fallback_understanding(message):
    """Deterministic multilingual fallback used when no LLM is configured or available."""
    import re
    m=_normalize_nlu_text(message)
    result={"intent":None,"entities":{},"confidence":0.0,"source":"rules"}

    order_terms=("commande", "commandes", "order", "orders", "طلب", "طلبات")
    order_actions=(
        "creer", "creation", "ajouter", "ajoute", "faire", "passer", "preparer", "etablir",
        "lancer", "enregistrer", "commander", "je veux", "je voudrais", "j'aimerais", "j ai besoin",
        "make", "place", "create", "prepare", "need", "want to", "add", "new", "please create",
        "إنشاء", "انشاء", "اضافة", "أريد", "اريد", "طلب جديد", "انشاء طلب", "إنشاء طلب"
    )
    client_terms=("client", "clients", "customer", "customers", "عميل", "عملاء", "زبون", "زبائن")
    supplier_terms=("fournisseur", "fournisseurs", "supplier", "suppliers", "مورد", "موردين")
    create_terms=("creer", "creation", "ajouter", "ajoute", "nouveau", "nouvelle", "add", "create", "new", "enregistrer", "إنشاء", "انشاء", "اضافة", "إضافة")
    search_terms=("chercher", "rechercher", "recherche", "trouver", "cherche", "find", "search", "look for", "consulter", "afficher", "montre", "liste", "بحث", "ابحث", "البحث", "عرض")
    edit_terms=("modifier", "modifie", "modification", "edit", "update", "change", "changer", "mettre a jour", "تعديل", "عدل", "تغيير")

    has_order=any(term in m for term in order_terms)
    has_action=any(term in m for term in order_actions)
    # "faire/passer une commande" and "je veux une commande" are valid creation requests.
    if has_order and (has_action or re.search(r"\b(une|la|nouvelle|une nouvelle|une commande)\b.*\bcommande\b",m)):
        result.update(intent="create_commande",confidence=0.78)
    else:
        entity="client" if any(term in m for term in client_terms) else "fournisseur" if any(term in m for term in supplier_terms) else None
        if entity:
            if any(term in m for term in create_terms) or (entity=="client" and re.search(r"\b(creer|ajouter|faire)\b.*\b(client|customer)\b",m)):
                result.update(intent=f"create_{entity}",confidence=0.75)
            elif any(term in m for term in edit_terms):
                result.update(intent=f"edit_{entity}",confidence=0.75)
            elif any(term in m for term in search_terms):
                result.update(intent=f"search_{entity}",confidence=0.72)

    # Low-risk entity extraction. These values are suggestions for the existing workflow,
    # never trusted as identifiers and always resolved/validated against the tenant database.
    quantity=re.search(r"\b(\d{1,7})\b\s*(?:unites?|pieces?|pcs?)?",m)
    if quantity:
        result["entities"]["quantity"]=int(quantity.group(1))
    email=re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",message or "")
    if email:
        result["entities"]["email"]=email.group(0)
    client_match=re.search(r"(?:\b(?:pour|du|de|au|client)\b)\s+(?:le\s+)?(?:client\s+)?[«\"']?([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",message or "",re.IGNORECASE)
    if client_match and result["intent"]=="create_commande":
        candidate=client_match.group(1).strip(" .,'\"»")
        stop_words=("avec", "et", "pour", "produit", "article", "quantite", "quantité", "de", "du")
        candidate=re.split(r"\s+(?:"+"|".join(stop_words)+r")\s+",candidate,flags=re.IGNORECASE)[0].strip()
        if candidate and candidate.lower() not in {"une", "un", "commande", "client", "mon", "ma", "mes"}:
            result["entities"]["client_name"]=candidate
    product_match=re.search(r"(?:produit|article)\s+(?:nomme\s+|appele\s+)?[«\"']?([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",message or "",re.IGNORECASE)
    if product_match and result["intent"]=="create_commande":
        result["entities"]["product_name"]=re.split(r"\s+(?:pour|avec|quantite|quantité|et)\s+",product_match.group(1),flags=re.IGNORECASE)[0].strip(" .,'\"»")
    named_match=re.search(r"(?:nomme|nommé|nommee|nommée|appele|appelé|appelee|appelée|named|name is)\s+[«\"']?([\wÀ-ÿ][\wÀ-ÿ .'-]{1,60})",message or "",re.IGNORECASE)
    if named_match:
        candidate=re.split(r"\s+(?:avec|et|email|e-mail|telephone|téléphone|adresse|phone)\s+",named_match.group(1),flags=re.IGNORECASE)[0].strip(" .,'\"»")
        if result["intent"]=="create_client": result["entities"]["client_name"]=candidate
        elif result["intent"]=="create_fournisseur": result["entities"]["supplier_name"]=candidate
    return result


def _understand_message(message, langue="fr"):
    """Use an optional OpenAI-compatible LLM for intent/entity extraction, with safe fallback.

    Configure OPENAI_API_KEY and optionally OPENAI_BASE_URL / OPENAI_MODEL in the root .env.
    The model only classifies the request; all ERP reads/writes remain in permission-checked code.
    """
    import json
    import os
    import re
    import httpx

    fallback=_fallback_understanding(message)
    api_key=os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback

    allowed={"create_commande","create_client","create_fournisseur","edit_client","edit_fournisseur",
             "search_client","search_fournisseur","analytics","general",None}
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    system=(
        "Tu es un classificateur NLU pour un ERP. Tu ne réponds pas à l'utilisateur et n'exécutes aucune action. "
        "Retourne exclusivement un objet JSON valide avec les clés intent, entities, confidence. "
        "intent doit être l'une de: create_commande, create_client, create_fournisseur, edit_client, "
        "edit_fournisseur, search_client, search_fournisseur, analytics, general, null. "
        "entities est un objet pouvant contenir client_name, product_name, quantity (entier), email, phone, address, field, value. "
        "N'invente aucune information; utilise null ou omets une entité absente. confidence est un nombre entre 0 et 1. "
        "Interprète les paraphrases en français, anglais et arabe, par exemple 'créer une commande', "
        "'faire une commande', 'passer une commande' et 'je voudrais commander' comme create_commande. "
        "Si la demande est ambiguë ou ne correspond pas à une action supportée, choisis general ou null."
    )
    try:
        response=httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            json={"model":model,"temperature":0,"response_format":{"type":"json_object"},
                  "messages":[{"role":"system","content":system},
                              {"role":"user","content":json.dumps({"message":message,"langue":langue},ensure_ascii=False)}]},
            timeout=5.0,
        )
        response.raise_for_status()
        content=response.json()["choices"][0]["message"]["content"]
        parsed=json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE))
        intent=parsed.get("intent")
        if intent not in allowed:
            return fallback
        # General/analytics requests continue through the existing deterministic handlers.
        if intent in {"general", "analytics"}:
            intent=None
        entities=parsed.get("entities") if isinstance(parsed.get("entities"),dict) else {}
        safe_entities={}
        for key in ("client_name","product_name","email","phone","address","field","value"):
            value=entities.get(key)
            if isinstance(value,str) and value.strip():
                safe_entities[key]=value.strip()[:200]
        quantity=entities.get("quantity")
        if isinstance(quantity,int) and 0 < quantity <= 1000000:
            safe_entities["quantity"]=quantity
        confidence=parsed.get("confidence",0)
        try: confidence=max(0.0,min(1.0,float(confidence)))
        except (TypeError,ValueError): confidence=0.0
        # Avoid launching a workflow from an uncertain model guess.
        if intent not in {None,"general","analytics"} and confidence < 0.55:
            return fallback
        return {"intent":intent,"entities":safe_entities,"confidence":confidence,"source":"llm"}
    except Exception:
        # The assistant must remain usable if the provider is unavailable or times out.
        return fallback


def _intent(m):
    """Backward-compatible wrapper for older tests/call sites."""
    return _fallback_understanding(m).get("intent")

def _answer_data(message,langue,user):
    m=message.lower().strip()
    if any(k in m for k in ["client","clients","customer","customers","زبون","زبائن","عميل","عملاء"]):
        if not _has_permission(user,"clients"): return _denied(langue,"clients")
        pool=_pool(user); conn=pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM client"); count=cur.fetchone()[0]
                cur.execute("SELECT nom FROM client ORDER BY nom LIMIT 10"); names=[r[0] for r in cur.fetchall()]
            if langue=="en": return f"There are {count} clients. First names: {', '.join(names) if names else 'none'}."
            if langue=="ar": return f"يوجد {count} عميلاً. من الأسماء الأولى: {', '.join(names) if names else 'لا يوجد'}."
            return f"Il y a {count} client(s). Premiers noms : {', '.join(names) if names else 'aucun'}."
        finally: pool.putconn(conn)
    if any(k in m for k in ["fournisseur","fournisseurs","supplier","suppliers","مورد","موردين"]):
        if not _has_permission(user,"fournisseurs"): return _denied(langue,"fournisseurs")
        pool=_pool(user); conn=pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM fournisseur"); count=cur.fetchone()[0]
                cur.execute("SELECT nom FROM fournisseur ORDER BY nom LIMIT 10"); names=[r[0] for r in cur.fetchall()]
            if langue=="en": return f"There are {count} suppliers. First names: {', '.join(names) if names else 'none'}."
            if langue=="ar": return f"يوجد {count} مورّد(ين). من الأسماء الأولى: {', '.join(names) if names else 'لا يوجد'}."
            return f"Il y a {count} fournisseur(s). Premiers noms : {', '.join(names) if names else 'aucun'}."
        finally: pool.putconn(conn)
    if any(k in m for k in ["stock","inventaire","inventory","produit","products","product","مخزون","مخزن","منتج"]):
        if not _has_permission(user,"stock"): return _denied(langue,"stock")
        pool=_pool(user); conn=pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN COALESCE(stock_actuel,0)<=0 THEN 1 ELSE 0 END),0) FROM produit"); total,rupture=cur.fetchone()
                cur.execute("SELECT nom, COALESCE(stock_actuel,0) FROM produit WHERE COALESCE(stock_actuel,0)<=5 ORDER BY stock_actuel, nom LIMIT 10"); low=cur.fetchall()
            lowtxt=', '.join(f"{n} ({s})" for n,s in low) if low else ('none' if langue=='en' else 'aucun')
            if langue=="en": return f"Stock contains {total} products. {rupture} are at zero or below. Low-stock products (<=5): {lowtxt}."
            if langue=="ar": return f"المخزون يحتوي على {total} منتجاً. عدد المنتجات التي مخزونها صفر أو أقل هو {rupture}. المنتجات ذات المخزون المنخفض (<=5): {lowtxt}."
            return f"Le stock contient {total} produit(s). {rupture} sont à zéro ou en dessous. Produits à faible stock (<=5) : {lowtxt}."
        finally: pool.putconn(conn)
    if any(k in m for k in ["facture","factures","invoice","invoices","billing","impay","payée","payees","فاتورة","فواتير"]):
        if not _has_permission(user,"facturation"): return _denied(langue,"facturation")
        pool=_pool(user); conn=pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN statut='impayee' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN statut='payee' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN statut='impayee' THEN montant_total ELSE 0 END),0) FROM facture"); total,unpaid,paid,amount=cur.fetchone()
            if langue=="en": return f"There are {total} invoices: {paid} paid and {unpaid} unpaid. Unpaid amount: {float(amount):.2f}."
            if langue=="ar": return f"يوجد {total} فاتورة: {paid} مؤداة و{unpaid} غير مؤداة. مبلغ غير المؤداة: {float(amount):.2f}."
            return f"Il y a {total} facture(s) : {paid} payée(s) et {unpaid} impayée(s). Montant impayé : {float(amount):.2f}."
        finally: pool.putconn(conn)
    if any(k in m for k in ["comptabil","accounting","balance","solde","achat","achats","account","محاسب","مشتريات","رصيد"]):
        if not _has_permission(user,"comptabilite"): return _denied(langue,"comptabilite")
        pool=_pool(user); conn=pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(SUM(CASE WHEN statut='payee' THEN montant_total ELSE 0 END),0), COALESCE(SUM(CASE WHEN statut='impayee' THEN montant_total ELSE 0 END),0) FROM facture"); paid,unpaid=cur.fetchone()
                cur.execute("SELECT COALESCE(SUM(montant_total),0) FROM achat WHERE statut <> 'annulee'"); purchases=cur.fetchone()[0]
            return f"Synthèse comptable : factures payées {float(paid):.2f}, factures impayées {float(unpaid):.2f}, achats {float(purchases):.2f}, solde commercial {float(paid-purchases):.2f}."
        finally: pool.putconn(conn)
    return None


def _period_clause(message):
    """Return a SQL date condition for the most common temporal requests."""
    m=message.lower()
    if "ce mois" in m or "ce mois-ci" in m or "this month" in m or "هذا الشهر" in m:
        return "date_commande >= date_trunc('month', CURRENT_DATE) AND date_commande < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'"
    if "aujourd" in m or "today" in m or "اليوم" in m:
        return "date_commande >= CURRENT_DATE AND date_commande < CURRENT_DATE + INTERVAL '1 day'"
    return "TRUE"


def _normalize_analytics_text(message):
    """Normalize common French/English input variations for analytics intents."""
    import unicodedata
    text=(message or "").lower().strip().replace("’", "'")
    text=text.replace("-", " ")
    text=" ".join(text.split())
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

def _analytics_answer(message, langue, user):
    """Answer read-only commercial analytics questions from the current tenant DB."""
    m=_normalize_analytics_text(message)
    sales_words=["vente","ventes","chiffre d'affaires","commandes","sales","revenue","orders","mبيعات","المبيعات","رقم المعاملات","طلبات"]
    top_product_words=["produit le plus vendu","produits les plus vendus","best seller","best-seller","top produit","top products","most sold","المنتجات الأكثر مبيعا","أكثر المنتجات مبيعا"]
    top_client_words=["client le plus actif","clients les plus actifs","meilleur client","meilleurs clients","top client","top clients","best customer","best customers","most valuable customer","العملاء الأكثر نشاطا","أفضل العملاء"]
    unpaid_words=["factures impayées","facture impayée","impayé","impayées","unpaid invoice","unpaid invoices","factures non payées","الفواتير غير المؤداة","فاتورة غير مؤداة"]
    summary_words=[
        "synthese des ventes", "synthese de ventes", "synthese des vente", "synthese de vente",
        "resume des ventes", "resume des vente", "resume commercial", "synthese commerciale",
        "sales summary", "commercial summary", "sales overview", "overview of sales",
        "ملخص المبيعات", "ملخص المبيعات التجارية", "ملخص تجاري"
    ]

    wants_summary=any(w in m for w in summary_words)
    wants_top_product=any(w in m for w in top_product_words)
    wants_top_client=any(w in m for w in top_client_words)
    wants_unpaid=any(w in m for w in unpaid_words)
    wants_sales=any(w in m for w in sales_words)
    if not (wants_summary or wants_top_product or wants_top_client or wants_unpaid or wants_sales):
        return None

    pool=_pool(user); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            if wants_unpaid and not wants_summary:
                if not _has_permission(user,"facturation","consulter"):
                    return _denied(langue,"facturation","consulter")
                cur.execute("""SELECT COUNT(*), COALESCE(SUM(montant_total),0)
                               FROM facture WHERE statut='impayee'""")
                count,amount=cur.fetchone()
                if langue=="en": return f"There are {count} unpaid invoice(s), for a total of {float(amount):.2f}."
                if langue=="ar": return f"يوجد {count} فاتورة غير مؤداة، بمبلغ إجمالي قدره {float(amount):.2f}."
                return f"Il y a {count} facture(s) impayée(s), pour un montant total de {float(amount):.2f}."

            if wants_top_product:
                if not _has_permission(user,"ventes","consulter"):
                    return _denied(langue,"ventes","consulter")
                clause=_period_clause(m)
                cur.execute(f"""SELECT p.nom, COALESCE(SUM(lc.quantite),0) AS quantite,
                                      COALESCE(SUM(lc.quantite*lc.prix_unitaire),0) AS ca
                               FROM ligne_commande lc
                               JOIN commande c ON c.id=lc.commande_id
                               JOIN produit p ON p.id=lc.produit_id
                               WHERE c.statut <> 'annulee' AND {clause}
                               GROUP BY p.id,p.nom ORDER BY quantite DESC, ca DESC LIMIT 5""")
                rows=cur.fetchall()
                if not rows:
                    return "Aucune vente de produit trouvée." if langue=="fr" else "No product sales found." if langue=="en" else "لم يتم العثور على مبيعات للمنتجات."
                if langue=="en":
                    return "Top products by quantity sold:\n"+"\n".join(f"- {n}: {q} unit(s), {float(ca):.2f}" for n,q,ca in rows)
                if langue=="ar":
                    return "أكثر المنتجات مبيعاً حسب الكمية:\n"+"\n".join(f"- {n}: {q} وحدة، {float(ca):.2f}" for n,q,ca in rows)
                return "Produits les plus vendus par quantité :\n"+"\n".join(f"- {n} : {q} unité(s), {float(ca):.2f}" for n,q,ca in rows)

            if wants_top_client:
                if not _has_permission(user,"ventes","consulter"):
                    return _denied(langue,"ventes","consulter")
                clause=_period_clause(m)
                cur.execute(f"""SELECT cl.nom, COUNT(c.id) AS nb_commandes,
                                      COALESCE(SUM(c.montant_total),0) AS ca
                               FROM commande c
                               JOIN client cl ON cl.id=c.client_id
                               WHERE c.statut <> 'annulee' AND {clause}
                               GROUP BY cl.id,cl.nom ORDER BY ca DESC LIMIT 5""")
                rows=cur.fetchall()
                if not rows:
                    return "Aucune commande trouvée." if langue=="fr" else "No orders found." if langue=="en" else "لم يتم العثور على طلبات."
                if langue=="en":
                    return "Top customers by revenue:\n"+"\n".join(f"- {n}: {nb} order(s), {float(ca):.2f}" for n,nb,ca in rows)
                if langue=="ar":
                    return "أفضل العملاء حسب رقم المعاملات:\n"+"\n".join(f"- {n}: {nb} طلب، {float(ca):.2f}" for n,nb,ca in rows)
                return "Top clients par chiffre d'affaires :\n"+"\n".join(f"- {n} : {nb} commande(s), {float(ca):.2f}" for n,nb,ca in rows)

            if wants_sales or wants_summary:
                if not _has_permission(user,"ventes","consulter"):
                    return _denied(langue,"ventes","consulter")
                clause=_period_clause(m)
                cur.execute(f"""SELECT COUNT(*), COALESCE(SUM(montant_total),0)
                               FROM commande WHERE statut <> 'annulee' AND {clause}""")
                nb_commandes,ca=cur.fetchone()
                cur.execute(f"""SELECT COUNT(*), COALESCE(SUM(montant_total),0)
                               FROM commande WHERE statut='confirmee' AND {clause}""")
                nb_conf,ca_conf=cur.fetchone()
                # One SQL read path for the four requested KPIs:
                # 1) number of non-cancelled orders
                # 2) total revenue
                # 3) number of confirmed orders
                # 4) confirmed-order revenue
                ca=float(ca or 0)
                ca_conf=float(ca_conf or 0)
                if langue=="en":
                    return (
                        "Sales summary\n"
                        f"- Number of orders: {nb_commandes}\n"
                        f"- Total revenue: {ca:.2f}\n"
                        f"- Confirmed orders: {nb_conf}\n"
                        f"- Confirmed-order revenue: {ca_conf:.2f}"
                    )
                if langue=="ar":
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

def _guide(lang,module):
    nom=MODULES.get(module,module)
    if lang=="en": return f"You are currently in {nom}. I can consult ERP data, create records, search clients or suppliers, and guide you through modifications, subject to your permissions."
    if lang=="ar": return f"أنت الآن في وحدة {nom}. يمكنني الاطلاع على بيانات ERP، إنشاء السجلات، البحث عن العملاء أو الموردين وإرشادك في التعديلات، حسب صلاحياتك."
    return f"Vous êtes actuellement dans {nom}. Je peux consulter les données ERP, créer des enregistrements, rechercher des clients ou fournisseurs et vous guider dans les modifications, selon vos permissions."

@router.post("/chat")
def chat(payload: AssistantMessage, utilisateur=Depends(utilisateur_connecte)):
    if not utilisateur.get("nomBase") or utilisateur.get("type")=="externe": raise HTTPException(403,"Assistant réservé aux collaborateurs de l'entreprise.")
    m=payload.message.lower().strip(); state=payload.state.model_copy(deep=True); prompts=_prompts(payload.langue)
    # Do not reclassify follow-up answers while a multi-step ERP workflow is active.
    understanding=_understand_message(payload.message,payload.langue) if not state.operation else {"intent":None,"entities":{}}
    intent=understanding.get("intent")
    entities=understanding.get("entities") or {}
    if intent:
        if intent == "create_commande":
            if not _has_permission(utilisateur,"ventes","creer"):
                return {"reply":_denied(payload.langue,"ventes","creer"),"state":AssistantState().model_dump()}
            if not _has_permission(utilisateur,"clients","consulter"):
                return {"reply":_denied(payload.langue,"clients","consulter"),"state":AssistantState().model_dump()}
            state=AssistantState(operation="create_commande",step="client",data={})
            client_name=entities.get("client_name")
            if client_name:
                rows=_find_entity(utilisateur,"client",client_name)
                exact=[row for row in rows if str(row.get("nom","")).strip().casefold()==client_name.strip().casefold()]
                selected=exact[0] if len(exact)==1 else rows[0] if len(rows)==1 else None
                if selected:
                    state.data={"client_id":selected["id"],"client_nom":selected["nom"],"lines":[]}
                    state.step="product"
                    reply=f"Client sélectionné : {selected['nom']}.\n\n{prompts['order_product']}" if payload.langue=="fr" else (f"Customer selected: {selected['nom']}.\n\n{prompts['order_product']}" if payload.langue=="en" else f"تم اختيار العميل: {selected['nom']}.\n\n{prompts['order_product']}")
                    return {"reply":reply,"state":state.model_dump()}
            return {"reply":prompts["order_client"],"state":state.model_dump()}
        entity=intent.split("_")[1]; module,_=_entity_meta(entity)
        action="creer" if intent.startswith("create") else "consulter" if intent.startswith("search") else "modifier"
        if not _has_permission(utilisateur,module,action): return {"reply":_denied(payload.langue,module,action),"state":AssistantState().model_dump()}
        if intent.startswith("create"):
            initial_data={}
            initial_name=entities.get("client_name") if entity=="client" else None
            if initial_name:
                initial_data["nom"]=initial_name
                state=AssistantState(operation=intent,step="email",data=initial_data)
                return {"reply":prompts["email"],"state":state.model_dump()}
            state=AssistantState(operation=intent,step="nom",data=initial_data); return {"reply":prompts["nom"],"state":state.model_dump()}
        if intent.startswith("search"):
            rows=_find_entity(utilisateur,entity,m)
            # Remove command words for a better query when possible.
            query=m
            for w in ["chercher","rechercher","recherche","trouver","cherche","find","search","look for","client","clients","customer","customers","fournisseur","fournisseurs","supplier","suppliers","بحث","ابحث","البحث","عميل","مورد"]: query=query.replace(w," ")
            rows=_find_entity(utilisateur,entity,query.strip()) if query.strip() else []
            state=AssistantState(); return {"reply":_format_search(rows,entity,payload.langue) if rows else prompts["search"],"state":state.model_dump()}
        state=AssistantState(operation=intent,step="search",data={}); return {"reply":prompts["search"],"state":state.model_dump()}

    op=state.operation; step=state.step; data=state.data
    if op == "create_commande":
        if step == "client":
            rows=_find_entity(utilisateur,"client",payload.message)
            if len(rows) != 1:
                return {"reply":_format_search(rows,"client",payload.langue)+"\n\n"+prompts["order_client"],"state":state.model_dump()}
            data["client_id"]=rows[0]["id"]; data["client_nom"]=rows[0]["nom"]; data["lines"]=[]; state.step="product"
            reply=f"Client sélectionné : {rows[0]['nom']}.\n\n{prompts['order_product']}"
        elif step == "product":
            rows=_search_products(utilisateur,payload.message)
            if len(rows) != 1:
                return {"reply":_format_products(rows,payload.langue)+"\n\n"+prompts["order_product"],"state":state.model_dump()}
            data["current_product"]={"id":rows[0]["id"],"nom":rows[0]["nom"],"prix":rows[0]["prix_unitaire"],"stock":rows[0]["stock_actuel"]}; state.step="quantity"
            reply=f"Produit sélectionné : {rows[0]['nom']} | Prix unitaire : {rows[0]['prix_unitaire']:.2f} | Stock disponible : {rows[0]['stock_actuel']}.\n\n{prompts['order_qty']}"
        elif step == "quantity":
            try: qty=int(payload.message.strip())
            except ValueError: qty=0
            cp=data.get("current_product",{})
            if qty <= 0: reply=prompts["order_qty"]
            elif qty > cp.get("stock",0): reply=f"Stock insuffisant : {cp.get('stock',0)} disponible(s).\n\n{prompts['order_qty']}"
            else:
                data["lines"].append({"produit_id":cp["id"],"nom":cp["nom"],"quantite":qty,"prix":cp["prix"]}); data.pop("current_product",None); state.step="more"
                reply=prompts["order_more"]
        elif step == "more":
            if _is_yes(m): state.step="product"; reply=prompts["order_product"]
            elif _is_no(m):
                total=sum(Decimal(str(x["prix"]))*x["quantite"] for x in data.get("lines",[])).quantize(Decimal("0.01")); data["total"]=float(total); state.step="confirmation"
                lines="\n".join(f"- {x['nom']} × {x['quantite']} = {Decimal(str(x['prix']))*x['quantite']:.2f}" for x in data["lines"])
                reply=f"Récapitulatif de la commande\nClient : {data['client_nom']}\n{lines}\nTotal : {total:.2f}\n\n{prompts['order_confirm']}"
            else: reply=prompts["order_more"]
        elif step == "confirmation":
            if _is_yes(m):
                result=_create_order(utilisateur,data["client_id"],data["lines"]); data["commande_id"]=result["id"]; data["numero"]=result["numero"]; state.step="facturation"
                reply=f"Commande {result['numero']} créée avec succès. Total : {result['total']:.2f}.\n\n{prompts['invoice']}"
            elif _is_no(m): state=AssistantState(); reply="Opération annulée." if payload.langue=="fr" else "Operation cancelled." if payload.langue=="en" else "تم إلغاء العملية."
            else: reply=prompts["order_confirm"]
        elif step == "facturation":
            if _is_yes(m):
                if not _has_permission(utilisateur,"facturation","creer"):
                    state=AssistantState(); reply=_denied(payload.langue,"facturation","creer")
                else:
                    inv=_create_invoice(utilisateur,data["commande_id"]); state=AssistantState(); reply=f"Facture {inv['numero']} créée avec succès."
            elif _is_no(m): state=AssistantState(); reply="Commande conservée sans facturation." if payload.langue=="fr" else "Order kept without invoicing." if payload.langue=="en" else "تم الاحتفاظ بالطلب بدون فوترة."
            else: reply=prompts["invoice"]
        else:
            state=AssistantState(); reply=_guide(payload.langue,payload.module)
        state.data=data; return {"reply":reply,"state":state.model_dump()}

    if op in {"create_client","create_supplier"}:
        entity="client" if op.endswith("client") else "fournisseur"; module,_=_entity_meta(entity)
        if step=="nom": data["nom"]=m; state.step="email"; reply=prompts["email"]
        elif step=="email": data["email"]="" if _is_skip(m) else payload.message.strip(); state.step="telephone"; reply=prompts["telephone"]
        elif step=="telephone": data["telephone"]="" if _is_skip(m) else payload.message.strip(); state.step="adresse"; reply=prompts["adresse"]
        elif step=="adresse": data["adresse"]="" if _is_skip(m) else payload.message.strip(); state.step="confirmation"; reply=_summary(entity,data,payload.langue)+"\n\n"+prompts["confirm"]
        elif step=="confirmation":
            if _is_yes(m):
                result=_create_entity(utilisateur,entity,data); state=AssistantState(); label=_label(entity,payload.langue); reply=(f"{label.capitalize()} created successfully: {result['nom']}." if payload.langue=="en" else f"تم إنشاء {label} بنجاح: {result['nom']}." if payload.langue=="ar" else f"Le {label} « {result['nom']} » a été créé avec succès.")
            elif _is_no(m): state=AssistantState(); reply="Operation cancelled." if payload.langue=="en" else "تم إلغاء العملية." if payload.langue=="ar" else "Opération annulée."
            else: reply=prompts["confirm"]
        else: state=AssistantState(); reply=_guide(payload.langue,payload.module)
        state.data=data; return {"reply":reply,"state":state.model_dump()}

    if op in {"edit_client","edit_supplier"}:
        entity="client" if op.endswith("client") else "fournisseur"; module,_=_entity_meta(entity)
        if step=="search":
            rows=_find_entity(utilisateur,entity,payload.message)
            if not rows: return {"reply":("No matching record was found. Please give another name." if payload.langue=="en" else "Aucun enregistrement trouvé. Donnez un autre nom." if payload.langue=="fr" else "لم يتم العثور على سجل مطابق. أعطني اسماً آخر."),"state":state.model_dump()}
            if len(rows)>1: return {"reply":_format_search(rows,entity,payload.langue)+"\n\n"+prompts["search"],"state":state.model_dump()}
            state.step="field"; state.data={"id":rows[0]["id"],"nom":rows[0]["nom"],"email":rows[0].get("email"),"telephone":rows[0].get("telephone"),"adresse":rows[0].get("adresse")}; return {"reply":_format_search(rows,entity,payload.langue)+"\n\n"+prompts["field"],"state":state.model_dump()}
        if step=="field":
            aliases={"nom":"nom","name":"nom","اسم":"nom","email":"email","e-mail":"email","البريد":"email","telephone":"telephone","téléphone":"telephone","phone":"telephone","هاتف":"telephone","adresse":"adresse","address":"adresse","العنوان":"adresse"}
            field=next((v for k,v in aliases.items() if k in m),None)
            if not field: return {"reply":prompts["field"],"state":state.model_dump()}
            state.data["field"]=field; state.step="value"; return {"reply":prompts["value"],"state":state.model_dump()}
        if step=="value":
            state.data["value"]=payload.message.strip(); state.step="confirmation"
            field=state.data["field"]; old=state.data.get(field) or ("non renseigné" if payload.langue=="fr" else "not provided" if payload.langue=="en" else "غير محدد")
            label={"fr":"client" if entity=="client" else "fournisseur","en":"customer" if entity=="client" else "supplier","ar":"العميل" if entity=="client" else "المورد"}[payload.langue]
            reply=f"Modification du {label} « {state.data['nom']} » :\n- {field} : {old} → {state.data['value']}\n\n{prompts['editconfirm']}" if payload.langue=="fr" else f"Modification for {label} “{state.data['nom']}”:\n- {field}: {old} → {state.data['value']}\n\n{prompts['editconfirm']}" if payload.langue=="en" else f"تعديل {label} «{state.data['nom']}»:\n- {field}: {old} ← {state.data['value']}\n\n{prompts['editconfirm']}"
            return {"reply":reply,"state":state.model_dump()}
        if step=="confirmation":
            if _is_yes(m):
                result=_update_entity(utilisateur,entity,state.data["id"],state.data["field"],state.data["value"]); state=AssistantState(); return {"reply":("Modification completed successfully." if payload.langue=="en" else "تم تعديل السجل بنجاح." if payload.langue=="ar" else "La modification a été enregistrée avec succès."),"state":state.model_dump()}
            if _is_no(m): return {"reply":("Operation cancelled." if payload.langue=="en" else "تم إلغاء العملية." if payload.langue=="ar" else "Modification annulée."),"state":AssistantState().model_dump()}
            return {"reply":prompts["editconfirm"],"state":state.model_dump()}

    answer=_analytics_answer(payload.message,payload.langue,utilisateur)
    if answer is None:
        answer=_answer_data(payload.message,payload.langue,utilisateur)
    if answer is None: answer=_guide(payload.langue,payload.module)
    return {"reply":answer,"module":payload.module,"langue":payload.langue,"state":AssistantState().model_dump()}
