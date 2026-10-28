"""ISO language code normalisation.

MKV stores ISO 639-2 codes; preferences are typed by humans as either
639-1 ("en", "hi") or 639-2 ("eng", "hin"). Everything is canonicalised to
**639-2/B** (the bibliographic form mkvmerge writes: ger, fre, chi, ...),
which is what our EBML parser reads.

No Qt imports: this module is pure and unit-tested.
"""

from __future__ import annotations

import re

# 639-1 -> 639-2/B
ISO1_TO_ISO2B: dict[str, str] = {
    "af": "afr", "am": "amh", "ar": "ara", "as": "asm", "az": "aze",
    "ba": "bak", "be": "bel", "bg": "bul", "bn": "ben", "bo": "tib",
    "br": "bre", "bs": "bos", "ca": "cat", "ceb": "ceb", "co": "cos",
    "cs": "cze", "cy": "wel", "da": "dan", "de": "ger", "dz": "dzo",
    "el": "gre", "en": "eng", "eo": "epo", "es": "spa", "et": "est",
    "eu": "baq", "fa": "per", "fi": "fin", "fil": "fil", "fo": "fao",
    "fr": "fre", "fy": "fry", "ga": "gle", "gd": "gla", "gl": "glg",
    "gu": "guj", "gv": "glv", "ha": "hau", "haw": "haw", "he": "heb",
    "hi": "hin", "hmn": "hmn", "hr": "hrv", "ht": "hat", "hu": "hun",
    "hy": "arm", "id": "ind", "ig": "ibo", "is": "ice", "it": "ita",
    "ja": "jpn", "jv": "jav", "ka": "geo", "kk": "kaz", "km": "khm",
    "kn": "kan", "ko": "kor", "ks": "kas", "ku": "kur", "ky": "kir",
    "la": "lat", "lb": "ltz", "lo": "lao", "lt": "lit", "lv": "lav",
    "mi": "mao", "mk": "mac", "ml": "mal", "mn": "mon", "mr": "mar",
    "ms": "may", "mt": "mlt", "my": "bur", "ne": "nep", "nl": "dut",
    "no": "nor", "oc": "oci", "or": "ori", "pa": "pan", "pl": "pol",
    "ps": "pus", "pt": "por", "rm": "roh", "ro": "rum", "ru": "rus",
    "sa": "san", "sd": "snd", "si": "sin", "sk": "slo", "sl": "slv",
    "so": "som", "sq": "alb", "sr": "srp", "su": "sun", "sv": "swe",
    "sw": "swa", "ta": "tam", "te": "tel", "tg": "tgk", "th": "tha",
    "tk": "tuk", "tl": "fil", "tr": "tur", "tt": "tat", "ug": "uig",
    "uk": "ukr", "ur": "urd", "uz": "uzb", "vi": "vie", "yi": "yid",
    "yo": "yor", "zh": "chi", "zu": "zul",
}

# 639-2/T -> 639-2/B (terminologic -> bibliographic)
ISO2T_TO_ISO2B: dict[str, str] = {
    "zho": "chi", "deu": "ger", "fra": "fre", "ces": "cze", "nld": "dut",
    "ron": "rum", "ell": "gre", "mya": "bur", "fas": "per", "sqi": "alb",
    "hye": "arm", "kat": "geo", "isl": "ice", "mkd": "mac", "mri": "mao",
    "msa": "may", "eus": "baq", "cym": "wel", "slk": "slo", "bod": "tib",
}

DISPLAY_NAMES: dict[str, str] = {
    "eng": "English", "hin": "Hindi", "jpn": "Japanese", "spa": "Spanish",
    "fre": "French", "ger": "German", "ita": "Italian", "por": "Portuguese",
    "rus": "Russian", "ara": "Arabic", "kor": "Korean", "chi": "Chinese",
    "tam": "Tamil", "tel": "Telugu", "mal": "Malayalam", "ben": "Bengali",
    "mar": "Marathi", "guj": "Gujarati", "kan": "Kannada", "pan": "Punjabi",
    "urd": "Urdu", "tur": "Turkish", "pol": "Polish", "dut": "Dutch",
    "swe": "Swedish", "nor": "Norwegian", "dan": "Danish", "fin": "Finnish",
    "cze": "Czech", "hun": "Hungarian", "rum": "Romanian", "gre": "Greek",
    "heb": "Hebrew", "tha": "Thai", "vie": "Vietnamese", "ind": "Indonesian",
    "may": "Malay", "fil": "Filipino", "ukr": "Ukrainian", "cat": "Catalan",
    "hrv": "Croatian", "srp": "Serbian", "slo": "Slovak", "slv": "Slovenian",
    "bul": "Bulgarian", "lit": "Lithuanian", "lav": "Latvian", "est": "Estonian",
    "ice": "Icelandic", "gle": "Irish", "wel": "Welsh", "baq": "Basque",
    "glg": "Galician", "afr": "Afrikaans", "swa": "Swahili", "zul": "Zulu",
    "amh": "Amharic", "nep": "Nepali", "sin": "Sinhala", "khm": "Khmer",
    "lao": "Lao", "bur": "Burmese", "mon": "Mongolian", "geo": "Georgian",
    "arm": "Armenian", "aze": "Azerbaijani", "kaz": "Kazakh", "uzb": "Uzbek",
    "per": "Persian", "pus": "Pashto", "kur": "Kurdish", "som": "Somali",
    "yor": "Yoruba", "ibo": "Igbo", "hau": "Hausa", "mao": "Maori",
    "mlt": "Maltese", "alb": "Albanian", "mac": "Macedonian", "bel": "Belarusian",
    "bos": "Bosnian", "tgk": "Tajik", "tuk": "Turkmen", "kir": "Kyrgyz",
    "tat": "Tatar", "bak": "Bashkir", "uig": "Uyghur", "tib": "Tibetan",
    "dzo": "Dzongkha", "jav": "Javanese", "sun": "Sundanese", "ceb": "Cebuano",
    "hmn": "Hmong", "haw": "Hawaiian", "lat": "Latin", "epo": "Esperanto",
    "yid": "Yiddish", "snd": "Sindhi", "asm": "Assamese", "ori": "Odia",
    "san": "Sanskrit", "kas": "Kashmiri", "bre": "Breton", "oci": "Occitan",
    "ltz": "Luxembourgish", "fao": "Faroese", "gla": "Scottish Gaelic",
    "roh": "Romansh", "fry": "Frisian", "cor": "Cornish", "glv": "Manx",
    "hat": "Haitian Creole", "cos": "Corsican", "und": "Undetermined",
}

_SPLIT_RE = re.compile(r"[,;\s]+")


def normalize_code(code: str | None) -> str:
    """Return the canonical 639-2/B code, or '' for empty input."""
    if not code:
        return ""
    value = str(code).strip().lower().replace("_", "-")
    if not value:
        return ""
    if "-" in value:  # en-US, zh-Hans, pt-BR
        value = value.split("-", 1)[0]
    if len(value) == 2:
        return ISO1_TO_ISO2B.get(value, value)
    return ISO2T_TO_ISO2B.get(value, value)


def is_known(code: str | None) -> bool:
    normalized = normalize_code(code)
    return bool(normalized) and normalized in DISPLAY_NAMES


def display_name(code: str | None) -> str:
    normalized = normalize_code(code)
    if not normalized:
        return ""
    return DISPLAY_NAMES.get(normalized, normalized.upper())


def parse_language_list(text: str | None) -> list[str]:
    """Parse 'en, hi; jpn' -> ['eng', 'hin', 'jpn'], order preserved, deduped."""
    if not text:
        return []
    result: list[str] = []
    for token in _SPLIT_RE.split(str(text).strip()):
        code = normalize_code(token)
        if code and code != "und" and code not in result:
            result.append(code)
    return result


def format_language_list(codes: list[str] | tuple[str, ...] | str | None) -> str:
    if isinstance(codes, str):
        codes = parse_language_list(codes)
    if not codes:
        return ""
    normalized = []
    for code in codes:
        value = normalize_code(code)
        if value and value not in normalized:
            normalized.append(value)
    return ",".join(normalized)


def language_choices() -> list[tuple[str, str]]:
    """(code, display name) pairs for autocomplete, alphabetised by name."""
    return sorted(DISPLAY_NAMES.items(), key=lambda item: item[1])
