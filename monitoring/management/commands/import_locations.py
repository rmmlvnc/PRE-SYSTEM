from django.core.management.base import BaseCommand

from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
from monitoring.models import Barangay, Purok
from monitoring.views import load_dengue_cases


class Command(BaseCommand):
    help = "Import Barangays and Puroks from dengue datasets"

    def handle(self, *args, **options):

        cases = load_dengue_cases()

        barangay_created = 0
        purok_created = 0

        for case in cases:

            barangay_name = canonicalize_barangay(case.get("barangay", ""))

            purok_name = str(
                case.get("purok", "")
            ).strip()

            # Skip rows without Barangay
            if not barangay_name:
                continue

            # ==========================================
            # BARANGAY
            # ==========================================

            barangay = (
                Barangay.objects
                .filter(
                    barangay_name__iexact=barangay_name
                )
                .first()
            )

            if not barangay:

                barangay = Barangay.objects.create(
                    barangay_name=barangay_name
                )

                barangay_created += 1

                self.stdout.write(
                    f"Created Barangay: {barangay_name}"
                )

            # ==========================================
            # PUROK
            # ==========================================

            if purok_name:

                exists = Purok.objects.filter(
                    barangay=barangay,
                    purok_name__iexact=purok_name
                ).exists()

                if not exists:

                    Purok.objects.create(
                        barangay=barangay,
                        purok_name=purok_name
                    )

                    purok_created += 1

                    self.stdout.write(
                        f"Created Purok: "
                        f"{purok_name} - "
                        f"{barangay_name}"
                    )

        # Ensure every official Iligan barangay is selectable, including a
        # barangay with no matching historical records yet.
        for barangay_name in ILIGAN_BARANGAYS:
            _, created = Barangay.objects.get_or_create(barangay_name=barangay_name)
            barangay_created += int(created)

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Import completed. "
                f"{barangay_created} Barangays created, "
                f"{purok_created} Puroks created."
            )
        )
