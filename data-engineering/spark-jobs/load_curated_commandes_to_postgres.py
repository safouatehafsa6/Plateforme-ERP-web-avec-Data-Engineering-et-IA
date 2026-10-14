
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv("/tmp/erp.env")

HOST = "postgres-erp"
USER = "erp_user"
PASSWORD = os.environ.get("ERP_DB_PASSWORD")

if not PASSWORD:
    raise RuntimeError("ERP_DB_PASSWORD n'est pas défini.")

# Bases déjà identifiées dans le projet
COMPANIES = {
    "compte_societe_test_ec11a6c3": 3,
    "compte_benjjedou_2061bc82": 4,
    "compte_demo_qr_897caff5": 5,
}

def connect(database):
    return psycopg2.connect(
        host=HOST,
        port=5432,
        dbname=database,
        user=USER,
        password=PASSWORD,
        connect_timeout=10,
    )

analytics = connect("erp_analytics")

try:
    with analytics:
        with analytics.cursor() as target:
            for database, company_id in COMPANIES.items():
                print(f"Découverte des métadonnées : {database}")

                source = connect(database)
                try:
                    with source.cursor() as cur:
                        # 1. Découvrir les tables
                        cur.execute("""
                            SELECT table_schema, table_name
                            FROM information_schema.tables
                            WHERE table_type = 'BASE TABLE'
                              AND table_schema NOT IN
                                  ('pg_catalog', 'information_schema')
                            ORDER BY table_schema, table_name
                        """)
                        tables = cur.fetchall()

                        # Remplacer les métadonnées précédentes
                        # de cette même entreprise et de cette base.
                        for table_name in (
                            "metadata_relationships",
                            "metadata_columns",
                            "metadata_tables",
                        ):
                            target.execute(
                                f"DELETE FROM public.{table_name} "
                                "WHERE company_id = %s "
                                "AND source_database = %s",
                                (company_id, database),
                            )

                        for schema, table in tables:
                            target.execute("""
                                INSERT INTO public.metadata_tables
                                    (company_id, source_database,
                                     table_schema, table_name)
                                VALUES (%s, %s, %s, %s)
                            """, (company_id, database, schema, table))

                        # 2. Découvrir les colonnes
                        cur.execute("""
                            SELECT table_schema, table_name,
                                   ordinal_position, column_name,
                                   data_type, is_nullable
                            FROM information_schema.columns
                            WHERE table_schema NOT IN
                                  ('pg_catalog', 'information_schema')
                            ORDER BY table_schema, table_name,
                                     ordinal_position
                        """)
                        columns = cur.fetchall()

                        for schema, table, position, column, dtype, nullable in columns:
                            target.execute("""
                                INSERT INTO public.metadata_columns
                                    (company_id, source_database,
                                     table_schema, table_name,
                                     ordinal_position, column_name,
                                     data_type, is_nullable)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                company_id, database, schema, table,
                                position, column, dtype,
                                nullable == "YES",
                            ))

                        # 3. Découvrir les vraies clés étrangères
                        cur.execute("""
                            SELECT tc.table_name,
                                   kcu.column_name,
                                   ccu.table_name,
                                   ccu.column_name,
                                   tc.constraint_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_catalog = kcu.constraint_catalog
                             AND tc.constraint_schema = kcu.constraint_schema
                             AND tc.constraint_name = kcu.constraint_name
                            JOIN information_schema.constraint_column_usage ccu
                              ON tc.constraint_catalog = ccu.constraint_catalog
                             AND tc.constraint_schema = ccu.constraint_schema
                             AND tc.constraint_name = ccu.constraint_name
                            WHERE tc.constraint_type = 'FOREIGN KEY'
                              AND tc.table_schema NOT IN
                                  ('pg_catalog', 'information_schema')
                            ORDER BY tc.table_name, kcu.column_name
                        """)
                        relationships = cur.fetchall()

                        for table, column, foreign_table, foreign_column, constraint in relationships:
                            target.execute("""
                                INSERT INTO public.metadata_relationships
                                    (company_id, source_database,
                                     table_name, column_name,
                                     foreign_table_name,
                                     foreign_column_name, constraint_name)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (
                                company_id, database, table, column,
                                foreign_table, foreign_column, constraint,
                            ))

                        print(
                            f"  Tables : {len(tables)} | "
                            f"Colonnes : {len(columns)} | "
                            f"Relations : {len(relationships)}"
                        )
                finally:
                    source.close()

    print("Découverte des métadonnées terminée.")

finally:
    analytics.close()
