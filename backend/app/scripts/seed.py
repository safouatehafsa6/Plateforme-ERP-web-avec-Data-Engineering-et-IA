import bcrypt
from dotenv import load_dotenv
load_dotenv()

from app.db import pool_central

EMAIL = "admin@benjeddou-erp.ma"
MOT_DE_PASSE = "Test1234!"


def seed():
    hash_ = bcrypt.hashpw(MOT_DE_PASSE.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO super_admin (nom, email, mot_de_passe)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET mot_de_passe = EXCLUDED.mot_de_passe
                """,
                ("Admin Test", EMAIL, hash_),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    print("Compte de test créé :")
    print("  email :", EMAIL)
    print("  mot de passe :", MOT_DE_PASSE)


if __name__ == "__main__":
    seed()
