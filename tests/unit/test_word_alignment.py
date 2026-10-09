from __future__ import annotations

import json

from domain.word_alignment import extract_word_alignment


def test_provider_words_align_only_to_exact_source_text() -> None:
    raw = json.dumps(
        {
            "utterances": [
                {
                    "text": "Hello, hello.",
                    "words": [
                        {"text": "Hello,", "start": 0, "end": 400},
                        {"text": "hello.", "start": 450, "end": 900},
                    ],
                }
            ]
        }
    ).encode()
    aligned = extract_word_alignment(raw, ("Hello, hello.",))
    assert len(aligned) == 1
    assert [(word.start_character, word.end_character) for word in aligned[0].words] == [
        (0, 6),
        (7, 13),
    ]
    assert extract_word_alignment(raw, ("Hello, edited.",)) == ()


def test_missing_or_invalid_word_timing_is_not_invented() -> None:
    raw = json.dumps(
        {"utterances": [{"text": "Hello", "words": [{"text": "Hello", "start": 5}]}]}
    ).encode()
    assert extract_word_alignment(raw, ("Hello",)) == ()
    assert extract_word_alignment(b"not-json", ("Hello",)) == ()
