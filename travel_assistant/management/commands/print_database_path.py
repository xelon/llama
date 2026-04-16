from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print the resolved default database file path (SQLite) for persistence checks."

    def handle(self, *args, **options):
        name = settings.DATABASES["default"]["NAME"]
        self.stdout.write(str(name))
