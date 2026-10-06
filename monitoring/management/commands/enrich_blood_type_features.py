from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from monitoring.ml.build_dataset import read_cases
from monitoring.ml.features import BLOOD_TYPES, BLOOD_TYPE_COLUMNS


class Command(BaseCommand):
    help = 'Add aggregated historical blood-type proportions to the monthly training dataset.'

    def handle(self, *args, **options):
        dataset_dir = Path(settings.BASE_DIR) / 'datasets'
        source = dataset_dir / 'integrated_monthly.csv'
        data = pd.read_csv(source)
        counts = defaultdict(Counter)

        cases = read_cases(dataset_dir)
        for case in cases.itertuples(index=False):
            if case.blood_type in BLOOD_TYPES:
                counts[(case.barangay, case.date.year, case.date.month)][case.blood_type] += 1

        for blood_type, column in zip(BLOOD_TYPES, BLOOD_TYPE_COLUMNS):
            values = []
            for row in data.itertuples(index=False):
                period_counts = counts[(row.barangay, int(row.year), int(row.month))]
                denominator = sum(period_counts.values())
                values.append(period_counts[blood_type] / denominator if denominator else 0.0)
            data[column] = values

        data.to_csv(source, index=False)
        self.stdout.write(self.style.SUCCESS(
            f'Updated {source.name} with {len(BLOOD_TYPE_COLUMNS)} aggregated blood-type features.'
        ))
