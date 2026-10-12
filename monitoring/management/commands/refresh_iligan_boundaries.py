"""Build the local hotspot GeoJSON from a full-resolution boundary extract.

The browser always reads ``static/data/iligan_barangays.geojson`` locally, so
the hotspot map remains available without exposing an API key or depending on
a boundary server at presentation time.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay


# The source uses longer display names for two existing PSGC barangays.
SOURCE_NAME_ALIASES = {
    'Acmac': 'Acmac-Mariano Badelles Sr.',
    'Mahayhay': 'Mahayahay',
    'Saray-Tibanga': 'Saray',
    'Saray (Saray-Tibanga)': 'Saray',
    'Tominobo Proper': 'Tomas L. Cabili',
    'Tomas L. Cabili (Tominobo Proper)': 'Tomas L. Cabili',
    'Tominobo Upper': 'Upper Tominobo',
}


class Command(BaseCommand):
    help = (
        'Create the local Iligan barangay boundary GeoJSON from a downloaded '
        'PSGC/NAMRIA GeoJSON extract.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--input',
            required=True,
            help='Path to the complete barangays.geojson source file.',
        )

    def handle(self, *args, **options):
        source_path = Path(options['input'])
        if not source_path.is_file():
            raise CommandError(f'Boundary source file was not found: {source_path}')

        try:
            source = json.loads(source_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(f'Could not read the boundary source: {error}') from error

        selected_features = []
        for feature in source.get('features', []):
            properties = feature.get('properties') or {}
            # Support the current PSGC/NAMRIA extract as well as the
            # higher-detail city file, whose legacy properties are NAME_2/3.
            if properties.get('ADM3_EN') != 'Iligan City' and properties.get('NAME_2') != 'Iligan City':
                continue

            source_name = properties.get('ADM4_EN') or properties.get('NAME_3', '')
            barangay_name = SOURCE_NAME_ALIASES.get(source_name) or canonicalize_barangay(source_name)
            if not barangay_name:
                raise CommandError(f'Unrecognised Iligan source barangay: {source_name!r}')

            selected_features.append({
                'type': 'Feature',
                'properties': {
                    'brgy_name': barangay_name,
                    'source_name': source_name,
                    'psgc_code': properties.get('psgc_code', ''),
                    'boundary_source': 'High-detail Philippine barangay boundary extract',
                },
                'geometry': feature.get('geometry'),
            })

        names = [feature['properties']['brgy_name'] for feature in selected_features]
        expected_names = set(ILIGAN_BARANGAYS)
        if len(selected_features) != 44 or set(names) != expected_names or len(names) != len(set(names)):
            missing = sorted(expected_names - set(names))
            unexpected = sorted(set(names) - expected_names)
            raise CommandError(
                'Boundary validation failed. '
                f'Expected 44 unique official barangays; got {len(selected_features)}. '
                f'Missing: {missing or "none"}; unexpected: {unexpected or "none"}.'
            )

        selected_features.sort(key=lambda feature: ILIGAN_BARANGAYS.index(feature['properties']['brgy_name']))
        output = {
            'type': 'FeatureCollection',
            'name': 'Iligan City barangay boundaries',
            'source': 'High-detail Philippine barangay boundaries; canonical labels validated against PSA PSGC',
            'features': selected_features,
        }
        target = Path(settings.BASE_DIR) / 'static' / 'data' / 'iligan_barangays.geojson'
        target.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'Wrote {len(selected_features)} validated Iligan barangay boundaries to {target}.'
        ))
