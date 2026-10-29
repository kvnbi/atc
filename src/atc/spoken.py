import re

DIGITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "niner": 9,
}
TEENS = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
SIDES = {"left": "L", "right": "R", "center": "C"}
PHONETIC = {
    word: word[0].upper()
    for word in (
        "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
        "november oscar papa quebec romeo sierra tango uniform victor whiskey yankee zulu"
    ).split()
}
PHONETIC["xray"] = "X"
NUMBERS = {**DIGITS, **TEENS, **TENS, "hundred": 0, "thousand": 0}


def tokens(text):
    return re.findall(r"[A-Za-z0-9]+|,", text)


def digit_run(words, i):
    j = i
    while j < len(words) and words[j] in DIGITS:
        j += 1
    return "".join(str(DIGITS[w]) for w in words[i:j]), j


def runways(words):
    found = []
    for i, word in enumerate(words):
        if word != "runway":
            continue
        digits, j = digit_run(words, i + 1)
        if 1 <= len(digits) <= 2:
            side = SIDES.get(words[j], "") if j < len(words) else ""
            found.append(digits.zfill(2) + side)
    return found


def frequencies(words):
    found = []
    i = 0
    while i < len(words):
        if words[i] not in DIGITS:
            i += 1
            continue
        whole, j = digit_run(words, i)
        if j < len(words) and words[j] == "point":
            fraction, k = digit_run(words, j + 1)
            if fraction:
                found.append(round(float(f"{whole}.{fraction}") * 1000))
                j = k
        i = j
    return found


def _group(words):
    if not words:
        return 1
    if all(w in DIGITS for w in words):
        return int("".join(str(DIGITS[w]) for w in words))
    return sum(NUMBERS[w] for w in words)


def _phrase(words):
    total, group = 0, []
    for word in words:
        if word == "thousand":
            total += _group(group) * 1000
            group = []
        elif word == "hundred":
            total += _group(group) * 100
            group = []
        else:
            group.append(word)
    return total + (_group(group) if group else 0)


def altitudes(words):
    found = []
    i = 0
    while i < len(words):
        if words[i] == "flight" and words[i + 1 : i + 2] == ["level"]:
            digits, j = digit_run(words, i + 2)
            if digits:
                found.append(("fl", int(digits) * 100))
            i = max(j, i + 1)
        elif words[i] in NUMBERS:
            j = i
            while j < len(words) and words[j] in NUMBERS:
                j += 1
            phrase = words[i:j]
            if "thousand" in phrase or "hundred" in phrase:
                found.append(("alt", _phrase(phrase)))
            i = j
        else:
            i += 1
    return found


def _after(words, keyword):
    for i, word in enumerate(words):
        if word == keyword:
            digits, _ = digit_run(words, i + 1)
            if digits:
                yield digits


def headings(words):
    return [int(d) for d in _after(words, "heading")]


def squawks(words):
    return list(_after(words, "squawk"))


def taxiways(words):
    found = []
    for i, word in enumerate(words):
        if word not in ("via", "taxiway"):
            continue
        name = ""
        for w in words[i + 1 :]:
            if w in PHONETIC:
                if name:
                    found.append(name)
                name = PHONETIC[w]
            elif w in DIGITS and name:
                name += str(DIGITS[w])
            elif w == ",":
                if name:
                    found.append(name)
                name = ""
            else:
                break
        if name:
            found.append(name)
    return found


DIGIT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner")
LETTER_WORDS = {letter: word for word, letter in PHONETIC.items()}
SIDE_WORDS = {"L": "left", "R": "right", "C": "center"}
DIGIT_CONTEXT = {"squawk", "heading", "runway", "frequency", "contact", "altimeter", "wind", "point"}


def _digits(text):
    return " ".join(DIGIT_WORDS[int(c)] for c in text if c.isdigit())


def spell(token):
    return " ".join(
        DIGIT_WORDS[int(c)] if c.isdigit() else LETTER_WORDS[c.upper()] for c in token if c.isalnum()
    )


def _altitude(value):
    thousands, rest = divmod(value, 1000)
    words = f"{_digits(str(thousands))} thousand"
    return words + (f" {DIGIT_WORDS[rest // 100]} hundred" if rest else "")


def _integer(match):
    previous = match.string[: match.start()].split()
    value = int(match[0])
    if (not previous or previous[-1].lower() not in DIGIT_CONTEXT) and 1000 <= value <= 60000 and value % 100 == 0:
        return _altitude(value)
    return _digits(match[0])


def normalize(text):
    text = re.sub(r"\bFL\s?(\d{2,3})\b", lambda m: "flight level " + _digits(m[1]), text, flags=re.I)
    text = re.sub(r"\bN\d{1,5}[A-Za-z]{0,2}\b", lambda m: spell(m[0]), text, flags=re.I)
    text = re.sub(r"\b([A-Z]{3,5})(\d)\b", lambda m: f"{m[1]} {DIGIT_WORDS[int(m[2])]}", text)
    text = re.sub(r"\b(\d{1,2})([LRClrc])\b", lambda m: f"{_digits(m[1])} {SIDE_WORDS[m[2].upper()]}", text)
    text = re.sub(r"\b(\d+)\.(\d+)\b", lambda m: f"{_digits(m[1])} point {_digits(m[2])}", text)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"(?<=\d)-(?=\d)", " ", text)
    text = re.sub(r"\b\d+\b", _integer, text)
    return re.sub(r"\s+", " ", text).strip()


def taxiway(name):
    return " ".join(LETTER_WORDS[c] if c.isalpha() else DIGIT_WORDS[int(c)] for c in name.upper() if c.isalnum())


def runway(name):
    side = SIDE_WORDS.get(name[-1:].upper())
    return f"{_digits(name[:-1] if side else name)}{' ' + side if side else ''}"
