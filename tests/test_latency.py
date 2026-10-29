import json

from atc.latency import LatencyLog, Stopwatch, describe


def test_the_first_sound_ends_the_clock_even_before_the_full_text_is_ready():
    log = LatencyLog()
    watch = Stopwatch("call", start=100.0, log=log)
    watch.mark("transcribed", 100.4)
    watch.mark("model", 100.5)
    watch.mark("audio", 101.6)
    watch.mark("transmit", 102.1)
    watch.mark("audio", 150.0)
    record = watch.finish()
    assert record["total"] == 1.6 and record["transmit"] == 2.1
    assert describe(record) == "[latency 1.6s: stt 0.4, reply 1.2]"
    assert watch.finish() is None and log.records == [record]


def test_turns_without_sound_are_not_logged():
    log = LatencyLog()
    watch = Stopwatch("event", start=0.0, log=log)
    watch.mark("transmit", 1.0)
    assert watch.finish() is None
    assert log.records == [] and log.median() is None


def test_typed_calls_have_no_transcription_time():
    watch = Stopwatch("call", start=10.0)
    watch.mark("audio", 11.5)
    assert describe(watch.finish()) == "[latency 1.5s: stt 0.0, reply 1.5]"


def test_log_appends_json_lines_and_reports_the_median(tmp_path):
    log = LatencyLog(tmp_path / "out" / "latency.jsonl")
    for total in (3.0, 1.0, 2.0):
        watch = log.stopwatch("call", start=0.0)
        watch.mark("audio", total)
        watch.finish()
    lines = (tmp_path / "out" / "latency.jsonl").read_text().splitlines()
    assert [json.loads(line)["total"] for line in lines] == [3.0, 1.0, 2.0]
    assert log.median() == 2.0
