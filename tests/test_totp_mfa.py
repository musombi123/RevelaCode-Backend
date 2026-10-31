import time
import unittest

from flask import Flask
from werkzeug.security import generate_password_hash

from backend import auth_gate as auth
from backend import mfa_routes as mfa


class TotpMfaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(auth.auth_bp)
        self.app.register_blueprint(mfa.mfa_bp)
        self.client = self.app.test_client()

        self.user = {
            "_id": "mfa-test-user",
            "contact": "mfa-test@example.test",
            "full_name": "MFA Test User",
            "password": generate_password_hash("correct horse battery staple"),
            "role": "user",
            "roles": ["user"],
            "verified": True,
            "mfa_enabled": False,
        }
        self.users = {self.user["contact"]: self.user}
        auth.MONGO_AVAILABLE = False
        auth.load_users_file = lambda: self.users
        auth.get_user_from_file = lambda contact: self.users.get(contact)
        auth.save_user_to_file = lambda user: self.users.__setitem__(user["contact"], user)
        self.access_token = auth.create_access_token(self.user)
        self.headers = {"Authorization": f"Bearer {self.access_token}"}
        self.app.add_url_rule(
            "/api/private-test",
            "private_test",
            lambda: {"success": True},
        )

    def test_totp_enrollment_login_challenge_and_replay_protection(self):
        status = self.client.get("/api/auth/mfa/status", headers=self.headers)
        self.assertEqual(status.status_code, 200, status.get_json())
        self.assertFalse(status.get_json()["enabled"])

        setup = self.client.post(
            "/api/auth/mfa/setup",
            headers=self.headers,
            json={"password": "correct horse battery staple"},
        )
        self.assertEqual(setup.status_code, 200, setup.get_json())
        secret = setup.get_json()["secret"]
        self.assertTrue(secret)
        self.assertTrue(setup.get_json()["otpauth_uri"].startswith("otpauth://totp/"))

        enabled = self.client.post(
            "/api/auth/mfa/enable",
            headers=self.headers,
            json={"code": mfa._totp_at(secret)},
        )
        self.assertEqual(enabled.status_code, 200, enabled.get_json())
        recovery_codes = enabled.get_json()["recovery_codes"]
        self.assertEqual(len(recovery_codes), 10)
        self.assertTrue(self.user["mfa_enabled"])
        self.assertIn(mfa._recovery_hash(recovery_codes[0]), self.user["mfa_recovery_code_hashes"])

        # A token issued before enrollment must not authorize protected APIs.
        old_session = self.client.get("/api/private-test", headers=self.headers)
        self.assertEqual(old_session.status_code, 401, old_session.get_json())
        self.assertEqual(old_session.get_json()["code"], "mfa_required")

        login = self.client.post(
            "/api/login",
            json={"contact": self.user["contact"], "password": "correct horse battery staple"},
        )
        self.assertEqual(login.status_code, 200, login.get_json())
        challenge = login.get_json()
        self.assertTrue(challenge["mfa_required"])
        self.assertIn("challenge_token", challenge)
        self.assertNotIn("access_token", challenge)

        verified = self.client.post(
            "/api/auth/mfa/login-verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": mfa._totp_at(secret),
            },
        )
        self.assertEqual(verified.status_code, 200, verified.get_json())
        self.assertTrue(verified.get_json()["mfa_verified"])
        self.assertTrue(verified.get_json()["access_token"])
        claims = auth.jwt.decode(
            verified.get_json()["access_token"],
            auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
        )
        self.assertTrue(claims["mfa_verified"])
        new_headers = {"Authorization": "Bearer " + verified.get_json()["access_token"]}
        valid_session = self.client.get("/api/private-test", headers=new_headers)
        self.assertEqual(valid_session.status_code, 200, valid_session.get_json())

        replay = self.client.post(
            "/api/auth/mfa/login-verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": mfa._totp_at(secret),
            },
        )
        self.assertEqual(replay.status_code, 401, replay.get_json())

    def test_recovery_codes_are_single_use(self):
        secret = mfa._new_secret()
        visible_codes, stored_hashes = mfa._new_recovery_codes()
        self.user.update({
            "mfa_enabled": True,
            "mfa_secret_enc": mfa._encrypt_secret(secret),
            "mfa_recovery_code_hashes": stored_hashes,
        })

        first_login = self.client.post(
            "/api/login",
            json={"contact": self.user["contact"], "password": "correct horse battery staple"},
        )
        self.assertTrue(first_login.get_json()["mfa_required"])
        first_verify = self.client.post(
            "/api/auth/mfa/login-verify",
            json={
                "challenge_token": first_login.get_json()["challenge_token"],
                "code": visible_codes[0],
            },
        )
        self.assertEqual(first_verify.status_code, 200, first_verify.get_json())
        self.assertNotIn(mfa._recovery_hash(visible_codes[0]), self.user["mfa_recovery_code_hashes"])

        second_login = self.client.post(
            "/api/login",
            json={"contact": self.user["contact"], "password": "correct horse battery staple"},
        )
        self.assertTrue(second_login.get_json()["mfa_required"])
        reused = self.client.post(
            "/api/auth/mfa/login-verify",
            json={
                "challenge_token": second_login.get_json()["challenge_token"],
                "code": visible_codes[0],
            },
        )
        self.assertEqual(reused.status_code, 401, reused.get_json())

    def test_privileged_login_is_allowed_when_optional_mfa_is_disabled(self):
        self.user["role"] = "admin"
        self.user["roles"] = ["admin"]
        self.user["mfa_enabled"] = False
        login = self.client.post(
            "/api/login",
            json={"contact": self.user["contact"], "password": "correct horse battery staple"},
        )
        self.assertEqual(login.status_code, 200, login.get_json())
        payload = login.get_json()
        self.assertFalse(payload.get("mfa_required", False))
        self.assertFalse(payload.get("mfa_setup_required", False))
        self.assertTrue(payload.get("access_token"))

        admin_headers = {"Authorization": "Bearer " + payload["access_token"]}
        protected = self.client.get("/api/private-test", headers=admin_headers)
        self.assertEqual(protected.status_code, 200, protected.get_json())
        self.assertFalse(self.user.get("mfa_enabled", False))


if __name__ == "__main__":
    unittest.main()
