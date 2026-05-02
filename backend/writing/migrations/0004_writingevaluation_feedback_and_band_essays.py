from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("writing", "0003_writingtopic"),
    ]

    operations = [
        migrations.AddField(
            model_name="writingevaluation",
            name="band_essays",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="writingevaluation",
            name="band_essays_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="writingevaluation",
            name="band_essays_status",
            field=models.CharField(default="pending", max_length=20),
        ),
        migrations.AddField(
            model_name="writingevaluation",
            name="criteria_feedback",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="writingevaluation",
            name="inline_suggestions",
            field=models.JSONField(default=list),
        ),
    ]
