from matchlens import calltrace


def test_nothing_is_recorded_outside_a_recording():
    calltrace.entered("Ingest")  # no error, no effect
    with calltrace.recording() as log:
        pass
    assert log == []


def test_entries_are_recorded_in_order():
    with calltrace.recording() as log:
        calltrace.entered("Spotting")
        calltrace.entered("Explanation")
    assert log == ["Spotting", "Explanation"]
