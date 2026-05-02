from rest_framework import serializers

from writing.models import WritingTopic


class WritingEvaluateRequestSerializer(serializers.Serializer):
    task_type = serializers.ChoiceField(choices=["task1", "task2"])
    prompt = serializers.CharField()
    essay = serializers.CharField()
    topic_image_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    topic_image = serializers.FileField(required=False, allow_null=True)


class WritingEvaluateResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    task_type = serializers.CharField()
    scores = serializers.DictField(child=serializers.FloatField())
    examiner_comments = serializers.CharField()
    corrections = serializers.ListField(child=serializers.DictField(), required=False)
    criteria_feedback = serializers.DictField(required=False)
    inline_suggestions = serializers.ListField(child=serializers.DictField(), required=False)
    word_count = serializers.IntegerField()
    band_essays_status = serializers.CharField(required=False)
    created_at = serializers.DateTimeField()


class WritingTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingTopic
        fields = [
            "id",
            "task_type",
            "title",
            "prompt",
            "topic_image_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "prompt": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        task_type = attrs.get("task_type", getattr(self.instance, "task_type", None))
        title = attrs.get("title", getattr(self.instance, "title", ""))
        prompt = attrs.get("prompt", getattr(self.instance, "prompt", ""))
        topic_image_url = attrs.get("topic_image_url", getattr(self.instance, "topic_image_url", None))

        title = (title or "").strip()
        prompt = (prompt or "").strip()

        if not title:
            raise serializers.ValidationError({"title": "Topic is required."})

        # Admin workflow: if prompt is not provided, use topic title as full prompt.
        attrs["title"] = title
        attrs["prompt"] = prompt or title

        if task_type == "task1" and not topic_image_url:
            raise serializers.ValidationError({"topic_image_url": "Task 1 topics require an image."})

        if task_type == "task2":
            attrs["topic_image_url"] = None

        return attrs
