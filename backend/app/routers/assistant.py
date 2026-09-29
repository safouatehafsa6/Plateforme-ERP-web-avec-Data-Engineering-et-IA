from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from fastapi import HTTPException
from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte

router = APIRouter(prefix="/api/assistant", tags=["assistant"] )

MODULES = {
    "dashboard": "Tableau de bord", "ventes": "Ventes", "achats": "Achats",
    "fournisseurs": "Fournisseurs", "clients": "Clients", "stock": "Stock",
    "facturation": "Facturation", "comptabilite": "Comptabilité",
    "parametres": "Paramètres", "collaborateurs": "Collaborateurs",
    "roles-permissions": "Rôles & Permissions", "utilisateurs-externes": "Utilisateurs externes",
}

class AssistantMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    langue: str = Field(default="fr", pattern="^(fr|en|ar)$")
    module: str = Field(default="dashboard", max_length=100)


def _reply(message: str, langue: str, module: str) -> str:
    m = message.lower().strip()
    module_nom = MODULES.get(module, module)
    if langue == "en":
        if any(k in m for k in ["stock", "inventory"]):
            return f"You are currently in {module_nom}. To manage stock, open Stock, select a product, then use the movement action for an entry, exit or adjustment. I can guide you step by step."
        if any(k in m for k in ["invoice", "billing", "facture"]):
            return f"You are in {module_nom}. The invoicing area lets you consult invoices and update their payment status. Ask me what you want to do and I will guide you."
        if any(k in m for k in ["client", "customer"]):
            return "In Clients, you can search, create and edit customers. Tell me whether you want to create, modify or search for a customer."
        if any(k in m for k in ["supplier", "fournisseur"]):
            return "In Suppliers, you can search, create and edit suppliers. I can guide you through the operation you want to perform."
        if any(k in m for k in ["accounting", "comptabilite"]):
            return "In Accounting, the current synthesis displays paid invoices, unpaid invoices, purchases and a commercial balance."
        return f"I am your ERP assistant. You are currently on {module_nom}. I can explain the current module, guide you through an operation, or help you find a feature."
    if langue == "ar":
        if any(k in m for k in ["مخزون", "stock", "مخزن"]):
            return f"أنت الآن في وحدة {module_nom}. لتدبير المخزون، افتح وحدة المخزون، اختر المنتج ثم استعمل حركة المخزون للدخول أو الخروج أو التعديل. يمكنني إرشادك خطوة بخطوة."
        if any(k in m for k in ["فاتورة", "فواتير", "فوترة"]):
            return f"أنت الآن في وحدة {module_nom}. يمكنك الاطلاع على الفواتير وتحديث حالة الأداء. أخبرني بالعملية التي تريد القيام بها وسأرشدك."
        if any(k in m for k in ["عميل", "زبون"]):
            return "في وحدة العملاء يمكنك البحث عن العملاء وإنشاؤهم وتعديلهم. أخبرني هل تريد إنشاء عميل أو تعديله أو البحث عنه."
        if any(k in m for k in ["مورد"]):
            return "في وحدة الموردين يمكنك البحث عن الموردين وإنشاؤهم وتعديلهم. يمكنني إرشادك في العملية التي تريد تنفيذها."
        if any(k in m for k in ["محاسبة"]):
            return "في وحدة المحاسبة، تعرض الخلاصة الفواتير المؤداة وغير المؤداة والمشتريات والرصيد التجاري."
        return f"أنا مساعد ERP الخاص بك. أنت الآن في وحدة {module_nom}. يمكنني شرح الوحدة الحالية أو إرشادك في عملية أو مساعدتك في العثور على وظيفة."
    if any(k in m for k in ["stock", "inventaire"]):
        return f"Vous êtes actuellement dans {module_nom}. Pour gérer le stock, ouvrez Stock, sélectionnez un produit puis utilisez l’action de mouvement pour une entrée, une sortie ou un ajustement. Je peux vous guider étape par étape."
    if any(k in m for k in ["facture", "facturation"]):
        return f"Vous êtes dans {module_nom}. La facturation permet de consulter les factures et de mettre à jour leur statut de paiement. Dites-moi ce que vous souhaitez faire et je vous guide."
    if any(k in m for k in ["client", "clients"]):
        return "Dans Clients, vous pouvez rechercher, créer et modifier des clients. Dites-moi si vous souhaitez créer, modifier ou rechercher un client."
    if any(k in m for k in ["fournisseur", "fournisseurs"]):
        return "Dans Fournisseurs, vous pouvez rechercher, créer et modifier des fournisseurs. Je peux vous guider dans l’opération souhaitée."
    if any(k in m for k in ["comptabilité", "comptabilite"]):
        return "Dans Comptabilité, la synthèse actuelle affiche les factures payées, les factures impayées, le total des achats et le solde commercial."
    return f"Je suis votre Assistant ERP. Vous êtes actuellement dans {module_nom}. Je peux expliquer le module actuel, vous guider dans une opération ou vous aider à trouver une fonctionnalité."

@router.post("/chat")
def chat(payload: AssistantMessage, utilisateur=Depends(utilisateur_connecte)):
    # L'assistant reste transversal, mais uniquement pour les collaborateurs
    # d'une entreprise disposant d'un environnement ERP.
    nom_base = utilisateur.get("nomBase")
    if not nom_base or utilisateur.get("type") == "externe":
        raise HTTPException(status_code=403, detail="Assistant réservé aux collaborateurs de l'entreprise.")
    if utilisateur.get("role") != "Admin":
        pool = get_pool_entreprise(nom_base); conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""SELECT 1 FROM utilisateur u JOIN role_permission rp ON rp.role_id=u.role_id JOIN permission p ON p.id=rp.permission_id WHERE u.id=%s AND u.actif=TRUE LIMIT 1""", (utilisateur.get("id"),))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=403, detail="Aucune permission métier active.")
        finally:
            pool.putconn(conn)
    return {"reply": _reply(payload.message, payload.langue, payload.module), "module": payload.module, "langue": payload.langue}
