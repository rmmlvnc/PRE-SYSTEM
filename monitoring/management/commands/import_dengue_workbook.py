"""Import corrected dengue case addresses from the yearly Excel workbook."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from monitoring.locations import canonicalize_barangay
from monitoring.models import Barangay, DengueCase, Purok, UserAccount


REQUIRED_COLUMNS = {
    'Sex', 'AgeYears', '(Current Address) Barangay',
    '(Current Address) Sitio / Purok / Street Name', 'DAdmit', 'BloodType',
}


def clean_text(value: object) -> str:
    """Return a trimmed cell value, treating spreadsheet blanks as empty."""
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


class Command(BaseCommand):
    help = 'Import dengue cases and corrected address data from a yearly-sheet Excel workbook.'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--workbook', type=Path, required=True, help='Path to the .xlsx workbook.')
        parser.add_argument('--dry-run', action='store_true', help='Validate the workbook without saving data.')

    def handle(self, *args, **options):
        workbook: Path = options['workbook']
        if not workbook.is_file():
            raise CommandError(f'Workbook not found: {workbook}')

        try:
            sheets = pd.read_excel(workbook, sheet_name=None, dtype=object)
        except ImportError as error:
            raise CommandError('Excel import requires openpyxl. Install the project requirements, including openpyxl, then retry.') from error
        except Exception as error:
            raise CommandError(f'Could not read workbook: {error}') from error

        rows = []
        skipped = 0
        for sheet_name, sheet in sheets.items():
            missing = REQUIRED_COLUMNS.difference(sheet.columns)
            if missing:
                raise CommandError(f'Sheet {sheet_name!r} is missing: {", ".join(sorted(missing))}')
            for source_index, record in sheet.iterrows():
                barangay_name = canonicalize_barangay(record['(Current Address) Barangay'])
                reported = pd.to_datetime(record['DAdmit'], errors='coerce')
                age = pd.to_numeric(record['AgeYears'], errors='coerce')
                if not barangay_name or pd.isna(reported) or pd.isna(age):
                    skipped += 1
                    continue
                purok_name = clean_text(record['(Current Address) Sitio / Purok / Street Name'])
                rows.append({
                    'sheet': str(sheet_name), 'source_row': int(source_index) + 2,
                    'barangay_name': barangay_name, 'purok_name': purok_name[:100],
                    'patient_age': max(0, int(age)),
                    'patient_sex': clean_text(record['Sex'])[:20] or 'Not specified',
                    'patient_blood_type': clean_text(record['BloodType']).upper().replace(' ', '')[:5],
                    'date_reported': reported.date(),
                })

        if not rows:
            raise CommandError('No valid dengue-case rows were found in the workbook.')
        self.stdout.write(f'Validated {len(rows)} rows; skipped {skipped} invalid rows.')
        if options['dry_run']:
            return

        importer, _ = UserAccount.objects.get_or_create(
            username='dataset_importer',
            defaults={
                'role': 'CHO', 'account_status': 'APPROVED', 'is_active': False,
                'first_name': 'Dataset', 'last_name': 'Importer',
            },
        )
        created_cases = created_puroks = 0
        with transaction.atomic():
            barangays = {item.barangay_name.casefold(): item for item in Barangay.objects.all()}
            for row in rows:
                barangay = barangays.get(row['barangay_name'].casefold())
                if barangay is None:
                    barangay = Barangay.objects.create(barangay_name=row['barangay_name'])
                    barangays[row['barangay_name'].casefold()] = barangay
                purok = None
                if row['purok_name']:
                    purok, created = Purok.objects.get_or_create(barangay=barangay, purok_name=row['purok_name'])
                    created_puroks += int(created)
                _, created = DengueCase.objects.get_or_create(
                    user_account=importer, barangay=barangay, purok=purok,
                    patient_age=row['patient_age'], patient_sex=row['patient_sex'],
                    patient_blood_type=row['patient_blood_type'], date_reported=row['date_reported'],
                    defaults={'case_status': 'Confirmed', 'remarks': f"Imported from workbook sheet {row['sheet']}, row {row['source_row']}."},
                )
                created_cases += int(created)

        self.stdout.write(self.style.SUCCESS(
            f'Import complete: {created_cases} new dengue cases and {created_puroks} corrected address records created.'
        ))
