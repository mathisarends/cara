import pytest

from stt.deepgram import StreamingSpeechToTextConfig


def test_keyterms_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="blank values"):
        StreamingSpeechToTextConfig(keyterms=["Cara", "  "])


def test_eager_end_of_turn_must_not_outrun_the_end_of_turn_threshold() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        StreamingSpeechToTextConfig(eot_threshold=0.5, eager_eot_threshold=0.6)


def test_eager_end_of_turn_is_compared_against_deepgrams_default_threshold() -> None:
    StreamingSpeechToTextConfig(eager_eot_threshold=0.7)

    with pytest.raises(ValueError, match="must not exceed"):
        StreamingSpeechToTextConfig(eager_eot_threshold=0.8)
