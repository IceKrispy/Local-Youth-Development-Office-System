from django.core.management.base import BaseCommand

from monitoring.age_rules import purge_aged_out_youths


class Command(BaseCommand):
    help = "Delete youth records whose birthdays already place them at age 31 or older."

    def handle(self, *args, **options):
        deleted_count = purge_aged_out_youths()
        self.stdout.write(
            self.style.SUCCESS(
                f"Age-out cleanup complete. Removed {deleted_count} youth record(s)."
            )
        )
