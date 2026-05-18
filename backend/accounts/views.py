from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import LoginSerializer, RegisterSerializer

User = get_user_model()

class RegisterAPIView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        if User.objects.filter(username=username).exists():
            return Response({"error": "username_taken"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, password=password)
        token, _ = Token.objects.get_or_create(user=user)
        avatar_url = None
        if hasattr(user, 'profile') and user.profile.avatar_url:
            avatar_url = user.profile.avatar_url

        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "avatar": avatar_url,
                },
            },
            status=status.HTTP_201_CREATED,
        )

class LoginAPIView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"error": "invalid_credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        token, _ = Token.objects.get_or_create(user=user)
        avatar_url = None
        if hasattr(user, 'profile') and user.profile.avatar_url:
            avatar_url = user.profile.avatar_url

        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "avatar": avatar_url,
                },
            }
        )

class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        avatar_url = None
        if hasattr(user, 'profile') and user.profile.avatar_url:
            avatar_url = user.profile.avatar_url
            
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "avatar": avatar_url,
            }
        )

class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"success": True})

class UpdateUsernameAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_username = request.data.get("username")
        if not new_username:
            return Response({"error": "username_required"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=new_username).exclude(id=request.user.id).exists():
            return Response({"error": "username_taken"}, status=status.HTTP_400_BAD_REQUEST)
        request.user.username = new_username
        request.user.save()
        return Response({"success": True})

from accounts.models import UserProfile

class UpdateAvatarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        avatar_url = request.data.get("avatar_url")
        if not avatar_url:
            return Response({"error": "avatar_url_required"}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.avatar_url = avatar_url
        profile.save()
        return Response({"success": True})

class CheckPasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        password = request.data.get("password")
        if not password:
            return Response({"error": "missing_password"}, status=status.HTTP_400_BAD_REQUEST)
        is_valid = request.user.check_password(password)
        return Response({"valid": is_valid})

class UpdatePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")
        if not current_password or not new_password:
            return Response({"error": "missing_fields"}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(current_password):
            return Response({"error": "wrong_password"}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save()
        return Response({"success": True})

class DeleteAccountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.delete()
        return Response({"success": True})
