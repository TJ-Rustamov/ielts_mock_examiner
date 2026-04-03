from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the default admin account for local development."

    def handle(self, *args, **options):
        user_model = get_user_model()
        username = "admin"
        password = "!@#$%QWERT"

        user, created = user_model.objects.get_or_create(username=username)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS("Admin user created: admin / !@#$%QWERT"))
        else:
            self.stdout.write(self.style.SUCCESS("Admin user updated: admin / !@#$%QWERT"))
