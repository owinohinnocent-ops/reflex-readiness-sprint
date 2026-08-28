import unittest
from datetime import timedelta

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth.dependencies import (
    get_current_user,
    require_dispatcher,
    require_retailer,
    require_rider,
)
from auth.passwords import hash_password, verify_password
from auth.tokens import create_access_token
from database.base import Base
from models.user import User, UserRole
from routes.auth import login
from schemas.auth import LoginRequest


class TestAuthentication(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            id=1,
            name="Retailer Alice",
            phone="0711000001",
            password_hash=hash_password("correct-password"),
            role=UserRole.RETAILER,
        )
        self.dispatcher = User(
            id=2,
            name="Dispatcher Bob",
            phone="0711000002",
            password_hash=hash_password("dispatcher-password"),
            role=UserRole.DISPATCHER,
        )
        self.db.add_all([self.user, self.dispatcher])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _credentials(self, token):
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_password_hashing_succeeds(self):
        password_hash = hash_password("secret")
        self.assertNotEqual(password_hash, "secret")
        self.assertTrue(password_hash.startswith("$argon2"))

    def test_password_verification_succeeds_for_correct_password(self):
        self.assertTrue(verify_password("correct-password", self.user.password_hash))

    def test_password_verification_fails_for_incorrect_password(self):
        self.assertFalse(verify_password("wrong-password", self.user.password_hash))

    def test_successful_login(self):
        response = login(LoginRequest(phone=self.user.phone, password="correct-password"), self.db)
        self.assertEqual(response.token_type, "bearer")
        self.assertTrue(response.access_token)
        self.assertEqual(
            get_current_user(self._credentials(response.access_token), self.db).id,
            self.user.id,
        )

    def test_unknown_phone_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            login(LoginRequest(phone="0799999999", password="correct-password"), self.db)
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Invalid phone or password")

    def test_incorrect_password_is_rejected_without_credential_disclosure(self):
        with self.assertRaises(HTTPException) as context:
            login(LoginRequest(phone=self.user.phone, password="wrong-password"), self.db)
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Invalid phone or password")

    def test_missing_and_invalid_tokens_are_rejected(self):
        with self.assertRaises(HTTPException) as missing:
            get_current_user(None, self.db)
        self.assertEqual(missing.exception.status_code, 401)
        with self.assertRaises(HTTPException) as invalid:
            get_current_user(self._credentials("not-a-token"), self.db)
        self.assertEqual(invalid.exception.status_code, 401)

    def test_expired_token_is_rejected(self):
        token = create_access_token(self.user.id, UserRole.RETAILER.value, timedelta(seconds=-1))
        with self.assertRaises(HTTPException) as context:
            get_current_user(self._credentials(token), self.db)
        self.assertEqual(context.exception.status_code, 401)

    def test_valid_token_resolves_correct_user(self):
        token = create_access_token(self.dispatcher.id, UserRole.DISPATCHER.value)
        current_user = get_current_user(self._credentials(token), self.db)
        self.assertEqual(current_user.id, self.dispatcher.id)
        self.assertEqual(current_user.role, UserRole.DISPATCHER)

    def test_correct_role_dependency_succeeds(self):
        self.assertIs(require_retailer(current_user=self.user), self.user)
        self.assertIs(require_dispatcher(current_user=self.dispatcher), self.dispatcher)

    def test_wrong_role_dependency_returns_403(self):
        with self.assertRaises(HTTPException) as context:
            require_dispatcher(current_user=self.user)
        self.assertEqual(context.exception.status_code, 403)
        with self.assertRaises(HTTPException) as context:
            require_rider(current_user=self.user)
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()