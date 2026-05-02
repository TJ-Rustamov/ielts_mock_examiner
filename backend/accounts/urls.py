from django.urls import path

from accounts.views import (
    LoginAPIView, LogoutAPIView, MeAPIView, RegisterAPIView,
    UpdateUsernameAPIView, UpdatePasswordAPIView, DeleteAccountAPIView,
    UpdateAvatarAPIView
)

urlpatterns = [
    path("register", RegisterAPIView.as_view(), name="auth-register"),
    path("login", LoginAPIView.as_view(), name="auth-login"),
    path("me", MeAPIView.as_view(), name="auth-me"),
    path("logout", LogoutAPIView.as_view(), name="auth-logout"),
    path("update-username", UpdateUsernameAPIView.as_view(), name="auth-update-username"),
    path("update-password", UpdatePasswordAPIView.as_view(), name="auth-update-password"),
    path("update-avatar", UpdateAvatarAPIView.as_view(), name="auth-update-avatar"),
    path("delete-account", DeleteAccountAPIView.as_view(), name="auth-delete-account"),
]
