from voice.wakeword.listener import WakeWordListener


def _listener(*, cooldown_chunks: int = 19) -> WakeWordListener:
    listener = WakeWordListener.__new__(WakeWordListener)
    listener._cooldown_chunks = cooldown_chunks
    listener._last_detection_sequence = None
    return listener


def test_is_past_cooldown_blocks_detections_within_the_chunk_window() -> None:
    """Regression test: a stalled event loop (e.g. a blocking Sonos HTTP call)
    can make two detections 6 audio chunks apart look 1.5+ wall-clock seconds
    apart, which defeated a wall-clock-based cooldown. Chunk distance is
    immune to that, since it only reflects audio content, not processing time.
    """
    listener = _listener(cooldown_chunks=19)

    assert listener._is_past_cooldown(56) is True
    assert (
        listener._is_past_cooldown(62) is False
    )  # 6 chunks later - still same utterance
    assert listener._is_past_cooldown(98) is True  # 36 chunks later - past cooldown


def test_is_past_cooldown_survives_a_sequence_jump_after_an_overrun() -> None:
    """After AudioOverrunError, the reader resumes at the live tail, so the
    next sequence number can jump far ahead. The gap it reflects is real
    audio time that actually passed, so it must count fully towards cooldown.
    """
    listener = _listener(cooldown_chunks=19)
    listener._last_detection_sequence = 62

    assert listener._is_past_cooldown(63) is False
    assert listener._is_past_cooldown(200) is True
