import base64
import os
import secrets
import pytest
from app.security import crypto

def setup_module():
    os.environ["ERP_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    os.environ["ERP_HMAC_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

def test_aes_gcm_round_trip_and_tamper():
    payload=b"backup postgres de test"
    encrypted=crypto.chiffrer(payload)
    assert encrypted.startswith(b"ERPENC1")
    assert crypto.dechiffrer(encrypted)==payload
    with pytest.raises(Exception):
        crypto.dechiffrer(encrypted[:-1]+bytes([encrypted[-1]^1]))

def test_hmac_sha256_detects_modification():
    payload=b"fichier de sauvegarde"
    signature=crypto.signer(payload)
    assert crypto.verifier_signature(payload,signature)
    assert not crypto.verifier_signature(payload+b"x",signature)

def test_argon2id_password_hash():
    hashed=crypto.hacher_mot_de_passe("MotDePasse!2026")
    assert hashed.startswith("$argon2id$")
    assert crypto.verifier_mot_de_passe("MotDePasse!2026",hashed)[0]
    assert not crypto.verifier_mot_de_passe("incorrect",hashed)[0]

def test_legacy_bcrypt_hash_requests_argon2_migration():
    bcrypt=pytest.importorskip("bcrypt")
    legacy=bcrypt.hashpw(b"AncienMdp!2026",bcrypt.gensalt()).decode()
    ok, migration=crypto.verifier_mot_de_passe("AncienMdp!2026",legacy)
    assert ok and migration


def test_optional_kms_envelope_with_mocked_provider(monkeypatch):
    import sys, types
    data_key=secrets.token_bytes(32)
    class FakeKMS:
        def generate_data_key(self, **kwargs):
            assert kwargs["KeySpec"]=="AES_256"
            return {"Plaintext":data_key,"CiphertextBlob":b"wrapped-data-key"}
        def decrypt(self, **kwargs):
            assert kwargs["CiphertextBlob"]==b"wrapped-data-key"
            return {"Plaintext":data_key}
    monkeypatch.setitem(sys.modules,"boto3",types.SimpleNamespace(client=lambda *a,**k:FakeKMS()))
    monkeypatch.setenv("ERP_KEY_PROVIDER","aws-kms")
    monkeypatch.setenv("AWS_KMS_KEY_ID","alias/erp-test")
    payload=b"backup via KMS"
    envelope=crypto.chiffrer(payload)
    assert envelope.startswith(b"ERPENC2")
    assert crypto.dechiffrer(envelope)==payload
