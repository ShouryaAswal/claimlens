"""
scripts/benchmark/log_capture.py
-----------------------------------
Captures the "citation integrity" metric: how many times the extraction
model cited a block_id that doesn't actually exist in the claim's
documents, and got caught and dropped before it could reach a human.

agents/section_extraction_agent.py already detects this (that's the
"anti-hallucination guard" described in its own module docstring) and
logs it via logger.warning(...) -- but it doesn't return the count
anywhere the caller can read it. Rather than editing that agent file to
add a return value (which would mean shipping a modified copy of a
tested Sprint 0-4 module), this attaches a logging.Handler to
`agents.section_extraction_agent`'s logger for the duration of one
claim's pipeline run and reads the count straight out of the log
record's args -- the exact same integer the agent already computed.

If agents/section_extraction_agent.py's warning message ever changes,
this will simply stop matching and report 0 -- it fails safe, not
silently wrong (the raw log line is still visible in stderr either way).
"""

from __future__ import annotations

import logging


_TARGET_LOGGER_NAME = "agents.section_extraction_agent"
_MESSAGE_MARKER = "model cited"  # from the f-string in section_extraction_agent.py


class HallucinationCaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.hallucinated_citation_count = 0
        self.affected_field_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if record.name != _TARGET_LOGGER_NAME:
            return
        msg_template = record.msg if isinstance(record.msg, str) else ""
        if _MESSAGE_MARKER not in msg_template:
            return
        # logger.warning("Section %r, field %r: model cited %d block_id(s) "
        #                 "not present in the corpus (%s) -- dropped from "
        #                 "evidence.", section_id, field_id, count, ids)
        try:
            count = int(record.args[2])  # type: ignore[index]
        except (TypeError, IndexError, ValueError):
            count = 1  # we know at least one hallucinated id triggered this
        self.hallucinated_citation_count += count
        self.affected_field_count += 1


class HallucinationTracker:
    """Context manager: attach/detach the handler around one claim run."""

    def __init__(self) -> None:
        self._handler: HallucinationCaptureHandler | None = None
        self._logger = logging.getLogger(_TARGET_LOGGER_NAME)

    def __enter__(self) -> "HallucinationTracker":
        self._handler = HallucinationCaptureHandler()
        self._logger.addHandler(self._handler)
        # Make sure WARNING-level records actually reach the handler even
        # if the root logger or this module's logger level was raised
        # elsewhere (e.g. by uvicorn config imported transitively).
        if self._logger.level == logging.NOTSET or self._logger.level > logging.WARNING:
            self._logger.setLevel(logging.WARNING)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._handler is not None:
            self._logger.removeHandler(self._handler)

    @property
    def hallucinated_citation_count(self) -> int:
        return self._handler.hallucinated_citation_count if self._handler else 0

    @property
    def affected_field_count(self) -> int:
        return self._handler.affected_field_count if self._handler else 0
