import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

securite = HTTPBearer()


def obtenir_utilisateur_courant(identifiants: HTTPAuthorizationCredentials = Depends(securite)) -> dict:
    """Décode et vérifie le token JWT. Toute route qui dépend de cette
    fonction est protégée : sans un token valide, l'accès est refusé —
    exactement le principe 'ne jamais faire confiance uniquement au
    Frontend' rappelé par l'entreprise."""
    try:
        payload = jwt.decode(
            identifiants.credentials,
            os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
            algorithms=["HS256"],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée, veuillez vous reconnecter.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide.")


def exiger_super_admin(utilisateur: dict = Depends(obtenir_utilisateur_courant)) -> dict:
    if utilisateur.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Accès réservé au Super Administrateur.")
    return utilisateur
