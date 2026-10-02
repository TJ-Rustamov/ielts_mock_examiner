"""Shared DRF permission classes.

Previously ``IsStaffOrSuperuser`` was defined separately in ``core.views`` and
``writing.views``; both now import it from here.
"""

from rest_framework.permissions import BasePermission


class IsStaffOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))
