import re


ILIGAN_BARANGAYS = (
    "Abuno", "Bonbonon", "Bunawan", "Buru-un", "Dalipuga", "Digkilaan",
    "Hinaplanon", "Kabacsanan", "Kiwalan", "Mahayahay", "Mainit",
    "Mandulog", "Maria Cristina", "Palao", "Poblacion", "Puga-an",
    "Rogongon", "Santa Elena", "Santa Filomena", "Suarez", "Tambacan",
    "Saray", "Tipanoy", "Tomas L. Cabili", "Upper Tominobo", "Tubod",
    "Bagong Silang", "Del Carmen", "Dulag", "San Miguel", "Santiago",
    "Santo Rosario", "Tibanga", "Acmac-Mariano Badelles Sr.", "Ditucalan",
    "Hindang", "Kalilangan", "Lanipao", "Luinab", "Panoroganan",
    "San Roque", "Ubaldo Laya", "Upper Hinaplanon", "Villa Verde",
)


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


_CANONICAL = {_key(name): name for name in ILIGAN_BARANGAYS}
_ALIASES = {
    "acmac": "Acmac-Mariano Badelles Sr.",
    "acmac mariano badelles": "Acmac-Mariano Badelles Sr.",
    "maria cristina": "Maria Cristina",
    "pala o": "Palao",
    "old poblacion": "Poblacion",
    "poblacion west": "Poblacion",
    "sta elena": "Santa Elena",
    "villa verde": "Villa Verde",
    "villaverde": "Villa Verde",
}


def canonicalize_barangay(value: object) -> str | None:
    """Return an official name, or None for an out-of-scope/unknown location."""
    key = _key(value)
    return _ALIASES.get(key) or _CANONICAL.get(key)
