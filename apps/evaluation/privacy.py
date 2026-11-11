"""Automated part of the privacy check on the generated datasets (Section 3.1.3, "Privacy check").

It confirms that every email address uses the reserved ztl.example domain, that no phone
numbers or payment card numbers appear, and that none of a list of real Nigerian
organisations is named. A person still reviews a sample by eye; this catches the
mechanical mistakes.
"""
import re
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE = re.compile(r"(?<!\d)(?:\+?234|0)[789][01]\d{8}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
ALLOWED_DOMAINS = {"ztl.example"}
REAL_ORGANISATIONS = [
    "GTBank", "Guaranty Trust", "Access Bank", "Zenith Bank", "First Bank", "UBA", "Union Bank", "Ecobank",
    "Sterling Bank", "Fidelity Bank", "Stanbic", "MTN", "Airtel", "Glo ", "Globacom", "9mobile", "Interswitch",
    "Flutterwave", "Paystack", "Opay", "Moniepoint", "Andela", "Galaxy Backbone", "NITDA", "FIRS", "LIRS",
    "Dangote", "Jumia", "Konga",
]
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".html", ".json", ".mbox"}


def check_folder(root):
    problems = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for domain in set(m.group(1).lower() for m in EMAIL.finditer(text)):
            if domain not in ALLOWED_DOMAINS:
                problems.append(f"{path}: email domain {domain}")
        if PHONE.search(text):
            problems.append(f"{path}: looks like a Nigerian phone number")
        for match in CARD.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if _luhn(digits):
                problems.append(f"{path}: looks like a payment card number")
        for name in REAL_ORGANISATIONS:
            if re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![a-z])", text):
                problems.append(f"{path}: names a real organisation ({name.strip()})")
    return problems


def _luhn(digits):
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0
