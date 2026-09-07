import os
import httpx

# Clé de TEST officielle de Google (valide toujours) - à remplacer en
# production par la vraie clé secrète, obtenue sur
# https://www.google.com/recaptcha/admin
SECRET_PAR_DEFAUT_TEST = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"


async def verifier_recaptcha(token: str | None) -> bool:
    if not token:
        return False

    secret = os.getenv("RECAPTCHA_SECRET_KEY") or SECRET_PAR_DEFAUT_TEST

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            reponse = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={"secret": secret, "response": token},
            )
            data = reponse.json()
            return data.get("success") is True
    except httpx.HTTPError:
        # Si Google est injoignable, on refuse par défaut (fail-safe sécurité).
        return False
