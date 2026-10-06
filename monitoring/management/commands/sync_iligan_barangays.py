from django.core.management.base import BaseCommand
from django.db import transaction

from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
from monitoring.models import Barangay, Purok


class Command(BaseCommand):
    help = 'Reconcile Barangay records to the official 44 City of Iligan labels.'

    @transaction.atomic
    def handle(self, *args, **options):
        canonical = {}
        created = 0
        merged = 0
        removed = 0

        for name in ILIGAN_BARANGAYS:
            barangay, was_created = Barangay.objects.get_or_create(barangay_name=name)
            canonical[name] = barangay
            created += int(was_created)

        for barangay in Barangay.objects.exclude(barangay_name__in=ILIGAN_BARANGAYS):
            target_name = canonicalize_barangay(barangay.barangay_name)
            if target_name:
                target = canonical[target_name]
                for purok in Purok.objects.filter(barangay=barangay):
                    if not Purok.objects.filter(barangay=target, purok_name__iexact=purok.purok_name).exists():
                        purok.barangay = target
                        purok.save(update_fields=['barangay'])
                barangay.delete()
                merged += 1
            else:
                barangay.delete()
                removed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Official barangays: {Barangay.objects.count()}. Created: {created}; '
            f'merged aliases: {merged}; removed out-of-scope labels: {removed}.'
        ))
