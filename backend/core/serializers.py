from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.models import AIConfiguration, SpeakingConfiguration, SpeakingQuestion
from speaking_app.models import SpeakingSession


User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    writing_tests = serializers.SerializerMethodField()
    speaking_tests = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "writing_tests",
            "speaking_tests",
        ]
        read_only_fields = ["id", "date_joined", "writing_tests", "speaking_tests"]

    def get_writing_tests(self, obj):
        return obj.writing_evaluations.count()

    def get_speaking_tests(self, obj):
        return SpeakingSession.objects.filter(candidate_metadata__user_id=obj.id).count()


class AdminUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(min_length=6)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_staff = serializers.BooleanField(required=False, default=False)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value


class AIConfigurationSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        enabled_models = attrs.get("enabled_models", getattr(self.instance, "enabled_models", [])) or []
        writing_model = attrs.get("writing_model", getattr(self.instance, "writing_model", ""))
        speaking_model = attrs.get("speaking_model", getattr(self.instance, "speaking_model", ""))

        if not enabled_models:
            raise serializers.ValidationError({"enabled_models": "Select at least one model."})

        if writing_model not in enabled_models:
            raise serializers.ValidationError({"writing_model": "Writing model must be one of enabled models."})
        if speaking_model not in enabled_models:
            raise serializers.ValidationError({"speaking_model": "Speaking model must be one of enabled models."})
        return attrs

    class Meta:
        model = AIConfiguration
        fields = [
            "provider",
            "enabled_models",
            "writing_model",
            "speaking_model",
            "writing_prompt",
            "speaking_prompt",
            "temperature",
            "max_tokens",
            "streaming_enabled",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class SpeakingConfigurationSerializer(serializers.ModelSerializer):
    def validate_speed(self, value):
        return max(0.5, min(2.0, float(value)))

    class Meta:
        model = SpeakingConfiguration
        fields = ["tts_provider", "voice", "speed", "updated_at"]
        read_only_fields = ["updated_at"]


class SpeakingQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakingQuestion
        fields = [
            "id",
            "part",
            "question",
            "follow_up",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_part(self, value):
        if value not in {1, 2, 3}:
            raise serializers.ValidationError("Part must be 1, 2, or 3.")
        return value
