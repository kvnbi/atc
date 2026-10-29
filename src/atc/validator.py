import re

from atc import spoken
from atc.data import airports as airport_data
from atc.data import nav

ACRONYMS = frozenset(
    "ILS VOR IFR VFR NDB DME RNAV GPS SID STAR ATIS METAR VHF UHF ATC AWOS ASOS RVR IMC VMC "
    "TCAS ADS LOC RNP CTAF NOTAM AGL MSL MVA MEA OK THE AND".split()
)
LEAKS = re.compile(r"not available|unavailable|no data|as an ai|language model", re.I)
EXTRA_FREQUENCIES = frozenset({121500, 122750})
MAX_ALTITUDE = 60000
KINDS = {"departure": "SID", "arrival": "STAR"}


def _procedures(tokens, words):
    found = []
    for i, token in enumerate(tokens[:-2]):
        if token.isalpha() and token.isupper() and words[i + 1] in spoken.DIGITS and words[i + 2] in KINDS:
            found.append((i, f"{token}{spoken.DIGITS[words[i + 1]]}", KINDS[words[i + 2]]))
    return found


def _is_fix(token):
    if nav.locate(token):
        return True
    return len(token) == 4 and airport_data.find(token) is not None


class Validator:
    __slots__ = ("_scope", "_retries", "_rejected", "history")

    def __init__(self, scope=lambda: (), retries=1):
        self._scope = scope
        self._retries = retries
        self.begin()

    def begin(self):
        self._rejected = 0
        self.history = []

    def reject(self, text, problems):
        self.history.append((text, tuple(problems)))
        self._rejected += 1
        return self._rejected <= self._retries

    def check(self, text):
        tokens = spoken.tokens(text)
        words = [t.lower() for t in tokens]
        airports = self._scope()
        problems = []
        if re.search(r"\d", text):
            problems.append(
                "spell every number as words, including the callsign "
                "(say 'Cessna one two three alpha bravo', never 'N123AB')"
            )
        if LEAKS.search(text):
            problems.append("do not mention missing data")
        problems += self._numbers(words, max((a.transition_alt for a in airports), default=0))
        problems += self._names(tokens, words, airports)
        if airports:
            problems += self._airport(words, airports)
        return list(dict.fromkeys(problems))

    def _numbers(self, words, transition):
        problems = []
        for kind, feet in spoken.altitudes(words):
            if feet % 100 or feet > MAX_ALTITUDE:
                problems.append(f"{feet} feet is not a valid altitude")
            elif transition and kind == "alt" and feet >= transition:
                problems.append("use a flight level at or above the transition altitude")
            elif transition and kind == "fl" and feet < transition:
                problems.append("flight levels are only used at or above the transition altitude")
        problems += [f"heading {h} is invalid" for h in spoken.headings(words) if not 1 <= h <= 360]
        problems += [
            f"squawk {s} is invalid"
            for s in spoken.squawks(words)
            if len(s) != 4 or any(c in "89" for c in s)
        ]
        return problems

    def _names(self, tokens, words, airports):
        problems = []
        procedures = _procedures(tokens, words)
        skip = {i for i, _, _ in procedures}
        for i, token in enumerate(tokens):
            if i in skip or not token.isalpha() or not token.isupper():
                continue
            if 3 <= len(token) <= 5 and token not in ACRONYMS and not _is_fix(token):
                problems.append(f"{token} is not a known fix")
        for _, name, kind in procedures:
            if airports and not any(name in nav.procedures(a.icao)[kind] for a in airports):
                problems.append(f"{name} is not a published {kind} here")
        return problems

    def _airport(self, words, airports):
        icaos = ", ".join(a.icao for a in airports)
        problems = []
        for runway in spoken.runways(words):
            if not any(a.runway_end(runway) for a in airports):
                problems.append(f"runway {runway} does not exist at {icaos}")
        if "center" not in words:
            known = EXTRA_FREQUENCIES.union(
                f for a in airports for values in a.frequencies.values() for f in values
            )
            for khz in spoken.frequencies(words):
                if khz not in known:
                    problems.append(f"{khz / 1000:.3f} is not a frequency at {icaos}")
        names = {e.name.upper() for a in airports for e in a.edges if not e.runway and e.name}
        for name in spoken.taxiways(words):
            if name not in names:
                problems.append(f"taxiway {name} does not exist at {icaos}")
        return problems
