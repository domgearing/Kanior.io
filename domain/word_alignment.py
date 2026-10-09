"""Derive display-only word positions from immutable provider output.

No timestamps or text offsets are inferred when provider words do not match the
current canonical transcript exactly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class AlignedWord:
    text: str
    start_ms: int
    end_ms: int
    start_character: int
    end_character: int


@dataclass(frozen=True)
class AlignedSegment:
    index: int
    words: tuple[AlignedWord, ...]


def extract_word_alignment(
    raw: bytes, segment_texts: tuple[str, ...]
) -> tuple[AlignedSegment, ...]:
    if not segment_texts:
        return ()
    try:
        value = json.loads(raw)
        utterances = value["utterances"]
    except (ValueError, KeyError, TypeError):
        return ()
    if not isinstance(utterances, list) or len(utterances) != len(segment_texts):
        return ()
    aligned: list[AlignedSegment] = []
    for index, (utterance, text) in enumerate(zip(utterances, segment_texts, strict=True)):
        if not isinstance(utterance, dict) or utterance.get("text") != text:
            return ()
        words = utterance.get("words")
        if not isinstance(words, list) or not words:
            continue
        aligned_words: list[AlignedWord] = []
        cursor = 0
        for item in words:
            if not isinstance(item, dict):
                return ()
            token, start, end = item.get("text"), item.get("start"), item.get("end")
            if (
                not isinstance(token, str)
                or not token
                or type(start) is not int
                or type(end) is not int
                or start < 0
                or end < start
            ):
                return ()
            position = text.find(token, cursor)
            if position < 0:
                return ()
            aligned_words.append(AlignedWord(token, start, end, position, position + len(token)))
            cursor = position + len(token)
        aligned.append(AlignedSegment(index, tuple(aligned_words)))
    return tuple(aligned)
