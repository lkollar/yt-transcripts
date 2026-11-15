from yt_transcripts.transcript import original_language, parse_json3, pick_track


def event(start_ms, text):
    return {"tStartMs": start_ms, "segs": [{"utf8": text}]}


def test_parse_json3_drops_rolling_overlap():
    data = {"events": [event(0, "hello there"), event(1000, "there general"), event(2000, "kenobi")]}
    assert parse_json3(data, timestamps=False) == "hello there general kenobi"


def test_parse_json3_timestamps():
    data = {"events": [event(0, "one"), event(3_661_000, "two"), {"tStartMs": 4_000_000}]}
    assert parse_json3(data, timestamps=True) == "[00:00:00] one\n[01:01:01] two"


def test_parse_json3_splits_paragraphs_at_sentence_end():
    sentence = "word " * 120 + "end."
    text = parse_json3({"events": [event(0, sentence), event(1000, "next")]}, timestamps=False)
    assert text.split("\n\n") == [" ".join(sentence.split()), "next"]


def test_original_language_prefers_original_audio():
    info = {"language": "ar", "formats": [{"format_note": "Arabic", "language": "ar"}, {"format_note": "English original", "language": "en-US"}]}
    assert original_language(info) == "en"


def test_original_language_falls_back():
    assert original_language({"language": "de-DE"}) == "de"
    assert original_language({}) == "en"


def test_pick_track_prefers_manual_and_orig():
    info = {
        "subtitles": {},
        "automatic_captions": {"en": ["translated"], "en-orig": ["asr"], "fr": ["fr"]},
    }
    assert pick_track(info, "en") == (["asr"], "automatic_captions:en-orig")
    info["subtitles"] = {"en-GB": ["manual"]}
    assert pick_track(info, "en") == (["manual"], "subtitles:en-GB")
    assert pick_track(info, "es") == (None, None)
