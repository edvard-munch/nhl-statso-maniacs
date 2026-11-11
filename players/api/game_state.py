"""Conservative state assertions from verified legacy evidence, without a clock."""

UNKNOWN = "unknown"
LIVE = "live"
FINAL = "final"
LEGACY_RESULT_SOURCE = "legacy_result"
LEGACY_FINAL_FLAG_SOURCE = "legacy_final_flag"
STATE_VALUES = (UNKNOWN, LIVE, FINAL)
STATE_SOURCES = (LEGACY_RESULT_SOURCE, LEGACY_FINAL_FLAG_SOURCE)


def state_evidence(is_final, *, is_live=False, final_result=False):
    """Only the verified result parser may supply live/final-result assertions.

    The flag's false value means final publication is incomplete, not that the
    upstream game is scheduled or live. Generic save timestamps cannot date
    either legacy assertion, so observation time remains explicitly unknown.
    """
    conflict = is_final and is_live
    value, source = UNKNOWN, None
    if not conflict:
        if is_live:
            value, source = LIVE, LEGACY_RESULT_SOURCE
        elif is_final:
            value, source = FINAL, LEGACY_FINAL_FLAG_SOURCE
        elif final_result:
            value, source = FINAL, LEGACY_RESULT_SOURCE
    return {"value": value, "source": source, "observed_at": None, "conflict": conflict}
