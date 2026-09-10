import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@benjeddou-erp.ma")


def envoyer_email(destinataire: str, sujet: str, corps_texte: str) -> None:
    """Envoie un email via SMTP. En développement, le serveur SMTP est
    Mailpit (voir docker-compose.yml) : les emails ne partent jamais
    réellement sur internet, ils sont consultables sur
    http://localhost:8025 — mais transitent par un vrai protocole email,
    jamais par les logs de l'application.
    """
    message = MIMEText(corps_texte, "plain", "utf-8")
    message["Subject"] = sujet
    message["From"] = SMTP_FROM
    message["To"] = destinataire

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as serveur:
        serveur.sendmail(SMTP_FROM, [destinataire], message.as_string())


def envoyer_code_otp(destinataire: str, code: str) -> None:
    sujet = "Votre code de vérification — BENJEDDOU ERP"
    corps = (
        f"Bonjour,\n\n"
        f"Voici votre code de vérification : {code}\n\n"
        f"Ce code expire dans 10 minutes. Ne le partagez avec personne.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n\n"
        f"— BENJEDDOU ERP"
    )
    envoyer_email(destinataire, sujet, corps)
