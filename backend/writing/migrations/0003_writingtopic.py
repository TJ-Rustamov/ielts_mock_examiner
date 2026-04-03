from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("writing", "0002_writingevaluation_author"),
    ]

    operations = [
        migrations.CreateModel(
            name="WritingTopic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_type", models.CharField(choices=[("task1", "Task 1"), ("task2", "Task 2")], max_length=10)),
                ("title", models.CharField(max_length=255)),
                ("prompt", models.TextField()),
                ("topic_image_url", models.URLField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
