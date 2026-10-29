import json
import statistics
import time
from pathlib import Path

TARGET_SECONDS = 2.5


class Stopwatch:
    __slots__ = ("label", "_start", "_marks", "_log", "_done")

    def __init__(self, label, start=None, log=None):
        self.label = label
        self._start = time.monotonic() if start is None else start
        self._marks = {}
        self._log = log
        self._done = False

    def mark(self, name, at=None):
        self._marks.setdefault(name, time.monotonic() if at is None else at)

    def finish(self):
        if self._done or "audio" not in self._marks:
            return None
        self._done = True
        marks = {name: round(at - self._start, 3) for name, at in self._marks.items()}
        record = {"label": self.label, "total": marks["audio"], **marks}
        if self._log:
            self._log.write(record)
        return record


class LatencyLog:
    def __init__(self, path=None):
        self._path = Path(path) if path else None
        self.records = []

    def stopwatch(self, label, start=None):
        return Stopwatch(label, start, self)

    def write(self, record):
        self.records.append(record)
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a") as f:
                f.write(json.dumps({"at": round(time.time()), **record}) + "\n")

    def median(self):
        totals = [r["total"] for r in self.records]
        return statistics.median(totals) if totals else None


def describe(record):
    stt = record.get("transcribed", 0.0)
    return f"[latency {record['total']:.1f}s: stt {stt:.1f}, reply {record['total'] - stt:.1f}]"
