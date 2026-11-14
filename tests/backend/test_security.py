from datetime import datetime, timedelta, timezone

from jose import jwt

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("Correct-Horse-9")
    assert hashed != "Correct-Horse-9" and verify_password("Correct-Horse-9", hashed)
    assert not verify_password("correct-horse-9", hashed)
    assert hash_password("Correct-Horse-9") != hashed  # salted


def test_token_roundtrip_carries_subject_and_role():
    payload = decode_access_token(create_access_token("5", "super_admin"))
    assert payload["sub"] == "5" and payload["role"] == "super_admin"


def test_tampered_token_is_rejected():
    token = create_access_token("5", "monitoring_officer")
    assert decode_access_token(token[:-3] + "abc") is None
    assert decode_access_token("not.a.token") is None


def test_token_signed_with_another_key_is_rejected():
    s = get_settings()
    forged = jwt.encode({"sub": "1", "role": "super_admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "some-other-secret", algorithm=s.jwt_algorithm)
    assert decode_access_token(forged) is None


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(get_settings(), "access_token_expire_minutes", -5)
    assert decode_access_token(create_access_token("5", "super_admin")) is None
