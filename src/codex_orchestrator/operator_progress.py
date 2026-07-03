from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from codex_orchestrator.operator_events import read_operator_events


def should_enable_live_progress(
    *,
    worker_mode: str,
    explicit: bool | None,
    stream: TextIO | None = None,
    environ: dict[str, str] | None = None,
) -> bool:
    env = os.environ if environ is None else environ
    if explicit is True:
        return True
    if explicit is False:
        return False
    env_value = env.get("CXOR_LIVE_PROGRESS")
    if env_value == "1":
        return True
    if env_value == "0":
        return False
    output = sys.stderr if stream is None else stream
    return worker_mode == "real_codex" and bool(getattr(output, "isatty", lambda: False)()) and not env.get("CI")


def format_operator_event_compact(event: dict, *, started_monotonic: float | None = None) -> str:
    elapsed = 0 if started_monotonic is None else max(0, int(time.monotonic() - started_monotonic))
    summary = event.get("summary") or event.get("event_type") or "operator event"
    return f"[cxor +{elapsed:03d}s] {summary}"


def format_operator_event_jsonl(event: dict) -> str:
    return json.dumps(event, sort_keys=True)


class OperatorProgressStreamer:
    def __init__(
        self,
        repo_root: Path,
        *,
        enabled: bool,
        progress_format: str = "compact",
        interval_seconds: float = 15.0,
        stream: TextIO | None = None,
        poll_seconds: float = 0.2,
    ) -> None:
        self.repo_root = repo_root
        self.enabled = enabled
        self.progress_format = progress_format
        self.interval_seconds = max(float(interval_seconds), 0.0)
        self.stream = sys.stderr if stream is None else stream
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_event_id: str | None = None
        self._started_monotonic = time.monotonic()
        self._last_output_monotonic = self._started_monotonic
        self._last_event: dict | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._run, name="cxor-operator-progress", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._drain_once()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._drain_once()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._drain_once()
            self._maybe_heartbeat()
            self._stop.wait(self.poll_seconds)

    def _drain_once(self) -> None:
        events = read_operator_events(self.repo_root, since=self._last_event_id)
        for event in events:
            self._last_event_id = event.get("event_id")
            self._last_event = event
            self._write_event(event)

    def _write_event(self, event: dict) -> None:
        if self.progress_format == "jsonl":
            line = format_operator_event_jsonl(event)
        else:
            line = format_operator_event_compact(event, started_monotonic=self._started_monotonic)
        print(line, file=self.stream, flush=True)
        self._last_output_monotonic = time.monotonic()

    def _maybe_heartbeat(self) -> None:
        if self.progress_format != "compact" or self.interval_seconds <= 0:
            return
        if time.monotonic() - self._last_output_monotonic < self.interval_seconds:
            return
        event = self._last_event
        if not event or event.get("event_type") != "patchlet_worker_started":
            return
        attempt_id = event.get("attempt_id") or "current attempt"
        prompt = event.get("prompt_path") or event.get("artifact_paths", [None])[0]
        print(
            format_operator_event_compact(
                {
                    "summary": f"worker {attempt_id} still running; prompt={prompt}",
                },
                started_monotonic=self._started_monotonic,
            ),
            file=self.stream,
            flush=True,
        )
        self._last_output_monotonic = time.monotonic()


@contextmanager
def operator_progress_streamer(
    repo_root: Path,
    *,
    enabled: bool,
    progress_format: str = "compact",
    interval_seconds: float = 15.0,
    stream: TextIO | None = None,
) -> Iterator[OperatorProgressStreamer]:
    streamer = OperatorProgressStreamer(
        repo_root,
        enabled=enabled,
        progress_format=progress_format,
        interval_seconds=interval_seconds,
        stream=stream,
    )
    streamer.start()
    try:
        yield streamer
    finally:
        streamer.stop()
