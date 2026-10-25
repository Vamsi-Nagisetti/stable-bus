
from Management.SessionManagement import SessionManagement


def test_session_management():
    session_management = SessionManagement()

    # 1. Create an access token
    user_id = 3
    token = session_management.create_access_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0
    print("Token created: True")

    # 2. Verify the token
    claims = session_management.verify_access_token(token)

    assert claims["sub"] == str(user_id)
    print("Token verified: True")

    # 3. Verify issuer and audience
    assert claims["iss"] == "stablebus"
    assert claims["aud"] == "stablebus-api"
    print("Issuer:", claims["iss"])
    print("Audience:", claims["aud"])

    # 4. Verify required claims exist
    required_claims = ["sub", "iss", "aud", "iat", "exp", "jti"]

    for claim in required_claims:
        assert claim in claims, f"Missing claim: {claim}"

    print("Required claims present: True")

    # 5. Verify a tampered token is rejected
    tampered_token = token[:-1] + (
        "A" if token[-1] != "A" else "B"
    )

    try:
        session_management.verify_access_token(tampered_token)
        raise AssertionError("Tampered token was accepted")
    except Exception as exc:
        # Don't accidentally swallow our own assertion failure.
        if isinstance(exc, AssertionError):
            raise
        print("Tampered token rejected: True")

    print("All SessionManagement tests passed!")


if __name__ == "__main__":
    test_session_management()
