"""Sauvegardes PostgreSQL chiffrées et vérifiables via pg_dump/pg_restore."""
import os, pathlib, subprocess, tempfile, time, uuid
from app.security.crypto import chiffrer, dechiffrer, signer, verifier_signature

def _dir():
    p=pathlib.Path(os.getenv("ERP_BACKUP_DIR","/app/backups")); p.mkdir(parents=True,exist_ok=True)
    try: os.chmod(p,0o700)
    except OSError: pass
    return p

def creer_sauvegarde(db_name:str)->dict:
    if not db_name.replace("_","").isalnum(): raise ValueError("Nom de base invalide.")
    with tempfile.TemporaryDirectory() as tmp:
        raw=pathlib.Path(tmp)/"db.dump"
        env=os.environ.copy()
        cmd=["pg_dump","--format=custom","--no-owner","--no-acl","--file",str(raw),"-h",env.get("DB_HOST","postgres-erp"),"-p",env.get("DB_PORT","5432"),"-U",env.get("DB_USER","erp_user"),db_name]
        env["PGPASSWORD"]=env.get("DB_PASSWORD","")
        result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=900)
        if result.returncode: raise RuntimeError("pg_dump a échoué : "+result.stderr[-1200:])
        plain=raw.read_bytes()
    encrypted=chiffrer(plain)
    name=f"{db_name}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.bak.enc"
    target=_dir()/name; target.write_bytes(encrypted); os.chmod(target,0o600)
    signature=signer(encrypted)
    (target.with_suffix(target.suffix+".hmac")).write_text(signature,encoding="ascii")
    os.chmod(target.with_suffix(target.suffix+".hmac"),0o600)
    return {"fichier":name,"base":db_name,"taille":len(encrypted),"hmac_sha256":signature,"chiffre":True}

def verifier_sauvegarde(filename:str)->dict:
    if pathlib.Path(filename).name!=filename or not filename.endswith(".bak.enc"): raise ValueError("Nom de sauvegarde invalide.")
    path=_dir()/filename; sigpath=path.with_suffix(path.suffix+".hmac")
    if not path.is_file() or not sigpath.is_file(): raise FileNotFoundError("Sauvegarde ou signature absente.")
    blob=path.read_bytes(); signature=sigpath.read_text(encoding="ascii").strip()
    if not verifier_signature(blob,signature): raise ValueError("Échec HMAC : fichier modifié ou clé incorrecte.")
    plain=dechiffrer(blob)
    with tempfile.NamedTemporaryFile(suffix=".dump") as f:
        f.write(plain); f.flush()
        env=os.environ.copy(); env["PGPASSWORD"]=env.get("DB_PASSWORD","")
        result=subprocess.run(["pg_restore","--list",f.name],env=env,capture_output=True,text=True,timeout=120)
        if result.returncode: raise ValueError("Le contenu PostgreSQL n'est pas un dump restaurable.")
    return {"fichier":filename,"integrite":"valide","dechiffrement":"valide","format":"PostgreSQL custom"}

def restaurer_sauvegarde(filename:str, db_name:str, confirmation:str)->dict:
    if confirmation != f"RESTAURER {db_name}": raise ValueError("Confirmation textuelle incorrecte.")
    verifier_sauvegarde(filename)
    # Filet de sécurité : snapshot chiffré automatique de l'état courant avant remplacement.
    sauvegarde_avant = creer_sauvegarde(db_name)
    blob=(_dir()/filename).read_bytes(); plain=dechiffrer(blob)
    with tempfile.NamedTemporaryFile(suffix=".dump") as f:
        f.write(plain); f.flush()
        env=os.environ.copy(); env["PGPASSWORD"]=env.get("DB_PASSWORD","")
        cmd=["pg_restore","--clean","--if-exists","--no-owner","--no-acl","-h",env.get("DB_HOST","postgres-erp"),"-p",env.get("DB_PORT","5432"),"-U",env.get("DB_USER","erp_user"),"-d",db_name,f.name]
        r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=1800)
        if r.returncode: raise RuntimeError("Restauration échouée : "+r.stderr[-1200:])
    return {"base":db_name,"restauration":"terminée","sauvegarde_avant_restauration":sauvegarde_avant["fichier"],"avertissement":"Une sauvegarde chiffrée de l'état précédent a été créée automatiquement."}
