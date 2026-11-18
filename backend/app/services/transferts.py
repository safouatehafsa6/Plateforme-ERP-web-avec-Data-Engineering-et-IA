"""Import/export métier sécurisé pour les tables autorisées du tenant courant."""
from __future__ import annotations
import csv, gzip, io, json, sqlite3, tarfile, zipfile, os, tempfile
from datetime import date, datetime
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring
from psycopg2 import sql

TABLES_AUTORISEES = {
    "client", "fournisseur", "produit", "commande", "achat", "bon_livraison",
    "devis", "facture", "ligne_achat", "ligne_bon_livraison", "ligne_commande",
    "ligne_devis", "ligne_facture", "mouvement_stock", "paiement", "departement",
}
FORMATS_IMPORT = {"csv", "xlsx", "json", "xml", "yaml", "sqlite", "dbf", "ods", "zip", "tar", "gz"}
FORMATS_EXPORT = FORMATS_IMPORT | {"ods", "rtf", "odt", "zip", "tar", "gz", "bak"}

def _json_value(v):
    if isinstance(v, (datetime, date)): return v.isoformat()
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, bytes): return v.hex()
    return v

def lire_lignes(cur, table, date_debut=None, date_fin=None, categorie=None):
    if table not in TABLES_AUTORISEES:
        raise ValueError("Table non autorisée.")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (table,))
    cols=[r[0] for r in cur.fetchall()]
    if not cols: raise ValueError("Table absente de cette base.")
    clauses=[]; params=[]
    date_col=next((c for c in ("date_creation","date","date_commande","date_achat","date_livraison","date_devis","date_facture","date_mouvement","date_paiement","created_at") if c in cols),None)
    cat_col=next((c for c in ("categorie","categorie_id","category","categorie_nom") if c in cols),None)
    if (date_debut or date_fin) and not date_col: raise ValueError("Aucune colonne de date reconnue pour cette table.")
    if date_debut: clauses.append(sql.SQL("{} >= %s").format(sql.Identifier(date_col))); params.append(date_debut)
    if date_fin:
        # Inclure toute la journée finale pour les colonnes timestamp.
        clauses.append(sql.SQL("{} < (%s + INTERVAL '1 day')").format(sql.Identifier(date_col))); params.append(date_fin)
    if categorie:
        if not cat_col: raise ValueError("Aucune colonne de catégorie reconnue pour cette table.")
        clauses.append(sql.SQL("{} = %s").format(sql.Identifier(cat_col))); params.append(categorie)
    q=sql.SQL("SELECT {} FROM {}").format(sql.SQL(",").join(map(sql.Identifier,cols)),sql.Identifier(table))
    if clauses: q += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
    q += sql.SQL(" ORDER BY 1")
    cur.execute(q,params)
    return cols, [[_json_value(v) for v in row] for row in cur.fetchall()]

def encoder(cols, rows, fmt):
    fmt=fmt.lower()
    records=[dict(zip(cols,row)) for row in rows]
    if fmt=="json": return json.dumps(records,ensure_ascii=False,indent=2,default=str).encode(), "application/json"
    if fmt=="csv":
        s=io.StringIO(newline=""); w=csv.DictWriter(s,fieldnames=cols); w.writeheader(); w.writerows(records)
        return s.getvalue().encode("utf-8-sig"),"text/csv; charset=utf-8"
    if fmt=="xlsx":
        from openpyxl import Workbook
        b=io.BytesIO(); wb=Workbook(); ws=wb.active; ws.title="Export"; ws.append(cols)
        for r in rows: ws.append([v if not isinstance(v,(dict,list)) else json.dumps(v,ensure_ascii=False) for v in r])
        wb.save(b); return b.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt=="xml":
        root=Element("rows")
        for row in records:
            node=SubElement(root,"row")
            for k,v in row.items(): SubElement(node,k.replace(" ","_")).text="" if v is None else str(v)
        return tostring(root,encoding="utf-8",xml_declaration=True),"application/xml"
    if fmt=="yaml":
        import yaml
        return yaml.safe_dump(records,allow_unicode=True,sort_keys=False).encode(),"application/yaml"
    if fmt=="sqlite":
        con=sqlite3.connect(":memory:")
        con.execute("CREATE TABLE export_data ("+",".join('"'+c.replace('"','""')+'" TEXT' for c in cols)+")")
        con.executemany("INSERT INTO export_data VALUES ("+",".join("?" for _ in cols)+")",rows)
        con.commit(); payload=con.serialize(); con.close()
        return payload,"application/vnd.sqlite3"
    if fmt=="dbf":
        import dbf
        # Les valeurs sont exportées en texte pour ne pas deviner les types métier.
        with tempfile.TemporaryDirectory() as tmp:
            path=os.path.join(tmp,"export.dbf")
            schema="; ".join(f"F{i+1} C(254)" for i,_ in enumerate(cols))
            table=dbf.Table(path,schema,codepage="cp1252"); table.open(mode=dbf.READ_WRITE)
            for row in rows:
                table.append(tuple("" if v is None else str(v)[:254] for v in row))
            table.close()
            with open(path,"rb") as f: payload=f.read()
        return payload,"application/x-dbf"
    if fmt in ("zip","tar","gz"):
        payload,mime=encoder(cols,rows,"csv")
        if fmt=="zip":
            b=io.BytesIO()
            with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z: z.writestr("donnees.csv",payload)
            return b.getvalue(),"application/zip"
        if fmt=="tar":
            b=io.BytesIO()
            with tarfile.open(fileobj=b,mode="w") as t:
                info=tarfile.TarInfo("donnees.csv"); info.size=len(payload); t.addfile(info,io.BytesIO(payload))
            return b.getvalue(),"application/x-tar"
        return gzip.compress(payload),"application/gzip"
    if fmt=="ods":
        from odf.opendocument import OpenDocumentSpreadsheet
        from odf.table import Table, TableRow, TableCell
        from odf.text import P
        b=io.BytesIO(); doc=OpenDocumentSpreadsheet(); tab=Table(name="Export"); doc.spreadsheet.addElement(tab)
        for row in [cols]+rows:
            tr=TableRow()
            for v in row:
                cell=TableCell(); cell.addElement(P(text="" if v is None else str(v))); tr.addElement(cell)
            tab.addElement(tr)
        doc.save(b); return b.getvalue(),"application/vnd.oasis.opendocument.spreadsheet"
    if fmt=="rtf":
        def esc(x): return str(x or "").replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n","\\line ")
        lines=["\\b "+" | ".join(map(esc,cols))+"\\b0"]
        lines += [" | ".join(esc(x) for x in r) for r in rows]
        return ("{\\rtf1\\ansi\\deff0\\pard "+ "\\par ".join(lines)+"}").encode("ascii","backslashreplace"),"application/rtf"
    if fmt=="odt":
        from odf.opendocument import OpenDocumentText
        from odf.text import P
        doc=OpenDocumentText()
        for row in [cols]+rows: doc.text.addElement(P(text=" | ".join("" if v is None else str(v) for v in row)))
        b=io.BytesIO(); doc.save(b); return b.getvalue(),"application/vnd.oasis.opendocument.text"
    raise ValueError("Format d'export non pris en charge.")

def decoder(data: bytes, fmt: str):
    fmt=fmt.lower()
    if fmt=="csv":
        text=data.decode("utf-8-sig"); return list(csv.DictReader(io.StringIO(text)))
    if fmt=="json":
        obj=json.loads(data.decode("utf-8")); return obj if isinstance(obj,list) else obj.get("rows",[])
    if fmt=="xlsx":
        from openpyxl import load_workbook
        ws=load_workbook(io.BytesIO(data),read_only=True,data_only=True).active
        it=ws.iter_rows(values_only=True); headers=[str(x) for x in next(it)]
        return [dict(zip(headers,r)) for r in it]
    if fmt=="yaml":
        import yaml
        obj=yaml.safe_load(data.decode("utf-8")); return obj if isinstance(obj,list) else obj.get("rows",[])
    if fmt=="xml":
        from defusedxml.ElementTree import fromstring
        root=fromstring(data); return [{c.tag:c.text for c in row} for row in root]
    if fmt=="ods":
        from odf.opendocument import load
        from odf.table import Table, TableRow, TableCell
        from odf.teletype import extractText
        doc=load(io.BytesIO(data)); tables=doc.spreadsheet.getElementsByType(Table)
        if not tables: raise ValueError("Aucune feuille ODS trouvée.")
        rows=[]
        for tr in tables[0].getElementsByType(TableRow):
            values=[]
            for cell in tr.getElementsByType(TableCell):
                values.append(extractText(cell))
            if values: rows.append(values)
        if not rows: return []
        headers=[str(x) for x in rows[0]]
        return [dict(zip(headers,row)) for row in rows[1:] if any(v!="" for v in row)]
    if fmt=="zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members=[m for m in archive.infolist() if not m.is_dir()]
            if len(members)!=1 or not members[0].filename.lower().endswith(".csv"):
                raise ValueError("L'archive ZIP doit contenir exactement un fichier CSV.")
            info=members[0]
            if info.file_size>25*1024*1024 or info.filename.startswith(("/","\\\\")) or ".." in info.filename.replace("\\\\","/").split("/"):
                raise ValueError("Archive ZIP non sûre ou trop volumineuse.")
            return decoder(archive.read(info), "csv")
    if fmt=="tar":
        with tarfile.open(fileobj=io.BytesIO(data),mode="r:*") as archive:
            members=[m for m in archive.getmembers() if m.isfile()]
            if len(members)!=1 or not members[0].name.lower().endswith(".csv"):
                raise ValueError("L'archive TAR doit contenir exactement un fichier CSV.")
            info=members[0]
            if info.size>25*1024*1024 or info.name.startswith(("/","\\\\")) or ".." in info.name.replace("\\\\","/").split("/"):
                raise ValueError("Archive TAR non sûre ou trop volumineuse.")
            stream=archive.extractfile(info)
            if stream is None: raise ValueError("Fichier CSV absent de l'archive.")
            return decoder(stream.read(25*1024*1024+1),"csv")
    if fmt=="gz":
        with gzip.GzipFile(fileobj=io.BytesIO(data),mode="rb") as stream:
            payload=stream.read(25*1024*1024+1)
        if len(payload)>25*1024*1024: raise ValueError("Archive GZ décompressée trop volumineuse.")
        return decoder(payload,"csv")
    if fmt=="dbf":
        from dbfread import DBF
        with tempfile.NamedTemporaryFile(suffix=".dbf") as f:
            f.write(data); f.flush()
            return [dict(r) for r in DBF(f.name,load=True,encoding="cp1252")]
    if fmt=="sqlite":
        con=sqlite3.connect(":memory:"); con.deserialize(data)
        names=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        if len(names)!=1: raise ValueError("Le fichier SQLite doit contenir exactement une table de données.")
        table=names[0][0]; cur=con.execute('SELECT * FROM "'+table.replace('"','""')+'"'); cols=[d[0] for d in cur.description]
        rows=[dict(zip(cols,r)) for r in cur.fetchall()]; con.close(); return rows
    raise ValueError("Format d'import non pris en charge. Formats acceptés : CSV, XLSX, JSON, XML, YAML et SQLite.")
