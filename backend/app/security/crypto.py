"""Chiffrement applicatif AES-256-GCM, HMAC-SHA-256 et dérivation Argon2id.

Les clés sont fournies hors du dépôt par le gestionnaire de secrets / variables
d'environnement. Ne jamais utiliser une clé par défaut en production.
"""
import base64, hashlib, hmac, os, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2 import PasswordHasher, exceptions as argon_exc

_hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2,hash_len=32,salt_len=16)

def _key(name):
    raw=os.getenv(name,"")
    if not raw: raise RuntimeError(f"Variable {name} obligatoire.")
    try: key=base64.urlsafe_b64decode(raw + "="*((4-len(raw)%4)%4))
    except Exception as e: raise RuntimeError(f"{name} doit être une clé Base64 URL-safe.") from e
    if len(key)!=32: raise RuntimeError(f"{name} doit décoder en exactement 32 octets.")
    return key

def _kms_client():
    import boto3
    region=os.getenv("AWS_REGION")
    return boto3.client("kms",region_name=region)

def _cle_chiffrement():
    """Retourne (clé AES-256, blob KMS enveloppé ou None)."""
    provider=os.getenv("ERP_KEY_PROVIDER","env").lower()
    if provider=="aws-kms":
        key_id=os.getenv("AWS_KMS_KEY_ID","")
        if not key_id: raise RuntimeError("AWS_KMS_KEY_ID obligatoire avec ERP_KEY_PROVIDER=aws-kms.")
        response=_kms_client().generate_data_key(KeyId=key_id,KeySpec="AES_256")
        return response["Plaintext"],response["CiphertextBlob"]
    if provider!="env": raise RuntimeError("ERP_KEY_PROVIDER doit valoir env ou aws-kms.")
    return _key("ERP_ENCRYPTION_KEY"),None

def _dechiffrer_cle(blob:bytes)->bytes:
    if os.getenv("ERP_KEY_PROVIDER","env").lower()!="aws-kms":
        raise RuntimeError("La sauvegarde utilise une clé KMS ; configurez ERP_KEY_PROVIDER=aws-kms.")
    response=_kms_client().decrypt(CiphertextBlob=blob)
    key=response["Plaintext"]
    if len(key)!=32: raise ValueError("La clé retournée par KMS n'est pas AES-256.")
    return key

def chiffrer(plaintext:bytes, aad:bytes=b"erp-backup-v1")->bytes:
    key,wrapped=_cle_chiffrement()
    nonce=secrets.token_bytes(12)
    ciphertext=AESGCM(key).encrypt(nonce,plaintext,aad)
    if wrapped:
        return b"ERPENC2"+len(wrapped).to_bytes(4,"big")+wrapped+nonce+ciphertext
    return b"ERPENC1"+nonce+ciphertext

def dechiffrer(envelope:bytes, aad:bytes=b"erp-backup-v1")->bytes:
    if envelope.startswith(b"ERPENC1") and len(envelope)>=35:
        key=_key("ERP_ENCRYPTION_KEY")
        nonce,ciphertext=envelope[7:19],envelope[19:]
    elif envelope.startswith(b"ERPENC2") and len(envelope)>=24:
        wrapped_len=int.from_bytes(envelope[7:11],"big")
        if wrapped_len<=0 or 11+wrapped_len+12>=len(envelope): raise ValueError("Enveloppe KMS invalide.")
        wrapped=envelope[11:11+wrapped_len]
        key=_dechiffrer_cle(wrapped)
        nonce=envelope[11+wrapped_len:23+wrapped_len]
        ciphertext=envelope[23+wrapped_len:]
    else:
        raise ValueError("Enveloppe de chiffrement invalide.")
    return AESGCM(key).decrypt(nonce,ciphertext,aad)

def signer(payload: bytes, context: str = "") -> str:
    """Signe un contenu avec un contexte optionnel."""
    contextual_payload = (
        context.encode("utf-8") + b"\0" + payload
        if context
        else payload
    )
    return hmac.new(
        _key("ERP_HMAC_KEY"),
        contextual_payload,
        hashlib.sha256
    ).hexdigest()


def verifier_signature(
    payload: bytes,
    signature: str,
    context: str = ""
) -> bool:
    """Vérifie la signature avec le contexte fourni."""
    return hmac.compare_digest(
        signer(payload, context),
        signature or ""
    )
def hacher_mot_de_passe(password:str)->str:
    return _hasher.hash(password)

def verifier_mot_de_passe(password:str, stored:str)->tuple[bool,bool]:
    """Retourne (valide, migration_requise)."""
    if stored.startswith("$argon2id$"):
        try: return _hasher.verify(stored,password), _hasher.check_needs_rehash(stored)
        except (argon_exc.VerifyMismatchError,argon_exc.VerificationError,argon_exc.InvalidHashError): return False,False
    if stored.startswith(("$2a$","$2b$","$2y$")):
        import bcrypt
        try: ok=bcrypt.checkpw(password.encode(),stored.encode())
        except ValueError: ok=False
        return ok,ok
    return False,False

def verifier_et_migrer(pool, table:str, user_id, password:str, stored:str)->bool:
    ok,migrate=verifier_mot_de_passe(password,stored)
    if ok and migrate:
        new_hash=hacher_mot_de_passe(password)
        # table est exclusivement fournie par les trois branches statiques du login.
        from psycopg2 import sql
        conn=pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("UPDATE {} SET mot_de_passe=%s WHERE id=%s").format(sql.Identifier(table)),(new_hash,user_id))
        finally: pool.putconn(conn)
    return ok
