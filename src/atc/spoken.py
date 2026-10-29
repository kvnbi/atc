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
