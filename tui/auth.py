"""
Cognito sign-in for the Y62DB Bindings TUI.

Same `USER_PASSWORD_AUTH` flow the web UI's Authenticator component uses
under the hood (and the same flow this project's `curl`-based live
verifications have used throughout — see docs/BLUEPRINT.md). The App
Client has no secret, so this is a single `InitiateAuth` call with no
`SECRET_HASH` needed.
"""

import boto3

from .config import AWS_REGION, USER_POOL_CLIENT_ID


class AuthError(Exception):
    """Raised for any sign-in failure — bad credentials, an unsupported
    challenge (e.g. NEW_PASSWORD_REQUIRED, MFA), or a transport error."""


def sign_in(username: str, password: str) -> str:
    """Returns a Cognito ID token for the given credentials, or raises AuthError."""
    client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        resp = client.initiate_auth(
            ClientId=USER_POOL_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
    except (
        client.exceptions.NotAuthorizedException,
        client.exceptions.UserNotFoundException,
    ):
        raise AuthError("Incorrect username or password.") from None
    except Exception as e:  # noqa: BLE001 - surface any other boto3/network error as a login failure
        raise AuthError(str(e)) from e

    result = resp.get("AuthenticationResult")
    if not result or "IdToken" not in result:
        challenge = resp.get("ChallengeName", "unknown")
        raise AuthError(
            f"Sign-in requires an additional step ({challenge}) not supported by this TUI."
        )
    return result["IdToken"]
