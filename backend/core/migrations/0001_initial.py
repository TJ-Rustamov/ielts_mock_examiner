from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AIConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="google", max_length=50)),
                ("writing_model", models.CharField(default="gemini-3.1-flash-lite-preview", max_length=120)),
                ("speaking_model", models.CharField(default="gemini-3.1-flash-lite-preview", max_length=120)),
                ("writing_prompt", models.TextField(blank=True, default="")),
                ("speaking_prompt", models.TextField(blank=True, default="")),
                ("temperature", models.FloatField(default=0.2)),
                ("max_tokens", models.PositiveIntegerField(default=2048)),
                ("streaming_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="SpeakingConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tts_provider", models.CharField(default="kokoro", max_length=50)),
                ("voice", models.CharField(default="af_heart", max_length=100)),
                ("speed", models.FloatField(default=1.0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="SpeakingQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("part", models.PositiveSmallIntegerField()),
                ("question", models.TextField()),
                ("follow_up", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["part", "-created_at"]},
        ),
    ]
