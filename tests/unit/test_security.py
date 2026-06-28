"""
Unit tests for security module — password hashing, JWT, and RBAC permissions.
"""
import pytest
from app.core.security import (
    Role, hash_password, verify_password,
    create_access_token, create_refresh_token, verify_access_token,
    has_permission, PERMISSIONS,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("SecretPass1!")
        assert hashed != "SecretPass1!"

    def test_correct_password_verifies(self):
        hashed = hash_password("SecretPass1!")
        assert verify_password("SecretPass1!", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("SecretPass1!")
        assert verify_password("WrongPass99!", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("SamePass1!")
        h2 = hash_password("SamePass1!")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_access_token_roundtrip(self):
        token = create_access_token(subject="user-123", role=Role.MANAGER)
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "manager"
        assert payload["type"] == "access"

    def test_refresh_token_rejected_as_access(self):
        refresh = create_refresh_token(subject="user-123")
        result  = verify_access_token(refresh)
        assert result is None  # wrong token type

    def test_invalid_token_returns_none(self):
        result = verify_access_token("not.a.real.token")
        assert result is None

    def test_admin_role_in_token(self):
        token   = create_access_token(subject="admin-1", role=Role.ADMIN)
        payload = verify_access_token(token)
        assert payload["role"] == "admin"


class TestRBAC:
    def test_admin_has_all_permissions(self):
        for perm in PERMISSIONS:
            assert has_permission(Role.ADMIN, perm), f"Admin should have {perm}"

    def test_viewer_can_read_analytics(self):
        assert has_permission(Role.VIEWER, "analytics:read") is True
        assert has_permission(Role.VIEWER, "heatmap:read")   is True
        assert has_permission(Role.VIEWER, "queue:read")     is True

    def test_viewer_cannot_manage_cameras(self):
        assert has_permission(Role.VIEWER, "cameras:write")  is False
        assert has_permission(Role.VIEWER, "cameras:delete") is False
        assert has_permission(Role.VIEWER, "users:write")    is False

    def test_manager_can_manage_cameras(self):
        assert has_permission(Role.MANAGER, "cameras:write") is True
        assert has_permission(Role.MANAGER, "zones:write")   is True
        assert has_permission(Role.MANAGER, "reports:export") is True

    def test_manager_cannot_manage_users_admin_level(self):
        assert has_permission(Role.MANAGER, "users:delete")   is False
        assert has_permission(Role.MANAGER, "cameras:delete") is False

    def test_unknown_permission_returns_false(self):
        assert has_permission(Role.ADMIN, "non_existent:permission") is False

    def test_role_hierarchy_ordering(self):
        from app.core.security import ROLE_HIERARCHY
        assert ROLE_HIERARCHY[Role.ADMIN]   > ROLE_HIERARCHY[Role.MANAGER]
        assert ROLE_HIERARCHY[Role.MANAGER] > ROLE_HIERARCHY[Role.VIEWER]
