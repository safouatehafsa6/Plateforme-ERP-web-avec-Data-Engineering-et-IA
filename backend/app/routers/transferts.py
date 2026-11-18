"""API d'import/export : périmètre limité aux tables métier explicitement autorisées."""
import io, os, subprocess, tempfile
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from psycopg2 import sql
from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin
from app.services import transferts

router=APIRouter(prefix="/api/transferts",tags=["import-export"])

@router.get("/formats")
def formats(utilisateur:dict=Depends(exiger_role_admin)):
    return {
      "import":["CSV","XLSX","ODS","JSON","XML","YAML","SQLite","DBF","ZIP","TAR","GZ"],
      "export":["CSV","XLSX","ODS","JSON","XML","YAML","DBF","SQLite","RTF","ODT","ZIP","TAR","GZ","BAK PostgreSQL"],
      "note":"CDX est un fichier d’index associé à certaines bases DBF, pas un format autonome de données."
    }

@router.get("/export/{table}")
def exporter(table:str, format:str=Query("csv"), date_debut:date|None=None, date_fin:date|None=None,
             categorie:str|None=None, utilisateur:dict=Depends(exiger_role_admin)):
    fmt=format.lower()
    if fmt not in transferts.FORMATS_EXPORT or fmt == "bak":
        raise HTTPException(422,"Format non disponible dans cette route. Les sauvegardes BAK sont gérées par le module de sauvegarde.")
    if date_debut and date_fin and date_debut>date_fin: raise HTTPException(422,"La date de début doit précéder la date de fin.")
    pool=get_pool_entreprise(utilisateur["nomBase"]); conn=pool.getconn()
    try:
        with conn.cursor() as cur:
            cols,rows=transferts.lire_lignes(cur,table,date_debut,date_fin,categorie)
        payload,mime=transferts.encoder(cols,rows,fmt)
    except ValueError as e: raise HTTPException(422,str(e))
    finally: pool.putconn(conn)
    return Response(payload,media_type=mime,headers={"Content-Disposition":f'attachment; filename="{table}_export.{fmt}"',"Cache-Control":"no-store"})

@router.post("/import/{table}")
async def importer(table:str, fichier:UploadFile=File(...), format:str|None=None,
                   utilisateur:dict=Depends(exiger_role_admin)):
    fmt=(format or (fichier.filename.rsplit(".",1)[-1] if fichier.filename and "." in fichier.filename else "")).lower()
    if fmt not in transferts.FORMATS_IMPORT: raise HTTPException(415,"Format non pris en charge.")
    data=await fichier.read()
    if len(data)>25*1024*1024: raise HTTPException(413,"Fichier limité à 25 Mo.")
    if table not in transferts.TABLES_AUTORISEES: raise HTTPException(403,"Table non autorisée.")
    try: records=transferts.decoder(data,fmt)
    except Exception as e: raise HTTPException(422,f"Fichier invalide : {e}")
    if fmt == "dbf" and records:
        # DBF limite les noms de champs à 10 caractères : on rétablit l'ordre
        # physique des colonnes de la table cible avant validation.
        pool=get_pool_entreprise(utilisateur["nomBase"]); c=pool.getconn()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(table,))
                db_cols=[r[0] for r in cur.fetchall()]
        finally: pool.putconn(c)
        records=[{col: list(row.values())[i] for i,col in enumerate(db_cols) if i < len(row) and col!="id"} for row in records]
    if not isinstance(records,list) or not records: raise HTTPException(422,"Le fichier ne contient aucune ligne.")
    if len(records)>10000: raise HTTPException(413,"Maximum 10 000 lignes par import.")
    if not all(isinstance(r,dict) for r in records): raise HTTPException(422,"Chaque ligne doit être un objet.")
    pool=get_pool_entreprise(utilisateur["nomBase"]); conn=pool.getconn(); inserted=0
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT column_name, is_generated, is_identity FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(table,))
                meta={r[0]:r[1:] for r in cur.fetchall()}
                if not meta: raise HTTPException(404,"Table inexistante.")
                allowed={c for c,(generated,identity) in meta.items() if generated=="NEVER" and identity=="NO" and c!="id"}
                for idx,record in enumerate(records,1):
                    unknown=set(record)-allowed
                    if unknown: raise HTTPException(422,f"Colonnes inconnues/interdites à la ligne {idx} : {', '.join(sorted(unknown))}")
                    cols=list(record)
                    if not cols: continue
                    q=sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(sql.Identifier(table),sql.SQL(",").join(map(sql.Identifier,cols)),sql.SQL(",").join(sql.Placeholder()*len(cols)))
                    cur.execute(q,[record[c] for c in cols]); inserted+=1
    finally: pool.putconn(conn)
    return {"message":"Import terminé dans une transaction.","table":table,"lignes_importees":inserted}
