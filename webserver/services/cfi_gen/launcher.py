#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Python launcher for the CFI batch generator (`cfi_batch.mjs`, same directory).

Runs ONE Node child process per book (never per annotation) — see
plan/WeChatReading_Annotation_Import_Plan.md §4.3 for the full design. This
module only shells out to the Node script and translates its stdin/stdout
JSON contract into Python types; all EPUB/DOM/CFI logic lives in
`cfi_batch.mjs`, which in turn delegates all CFI generation/serialization to
the vendored `third-party/foliate-js/epubcfi.js` (see plan §4.2 for why).

Path to the Node script is resolved relative to this file (`__file__`), not
CWD or a config value — this is the same pattern already used elsewhere in
the codebase (`webserver/settings.py`'s `os.path.dirname(__file__)`-based
paths, `webserver/toolbox/chinese_converter/opencc_engine.py`) and is what
makes it work unchanged both in a local checkout and inside the Docker image
(see plan §4.3 "路径解析" and the `COPY third-party/foliate-js/ ...` lines
added to `Dockerfile`).
@author: PoxenStudio, 2026-06
"""

import asyncio
import json
import logging
import os
from typing import List, Literal, Optional, TypedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
NODE_SCRIPT = os.path.join(_HERE, "cfi_batch.mjs")

DEFAULT_TIMEOUT_SECONDS = 60
# Keep in sync with MAX_ANCHORS in cfi_batch.mjs — checked here too so we
# fail fast without even spawning the subprocess.
MAX_ANCHORS = 2000

OnAmbiguous = Literal["error", "first_match"]


class CfiAnchor(TypedDict, total=False):
    id: str
    text: str  # omit/empty -> chapter-start fallback, see cfi_batch.mjs / plan §4.5
    chapterHint: str


class CfiResult(TypedDict, total=False):
    id: str
    status: str  # "ok" | "no_match" | "ambiguous" | "error"
    cfi: str
    matchCount: int
    ambiguousResolution: str
    degraded: str
    error: str


class CfiBatchError(Exception):
    """A whole-book failure: non-zero exit, unexpected stderr output, a
    timeout, or a malformed response from the Node subprocess.

    Callers MUST treat this as "the whole book failed" and surface it as
    such — never catch it and silently treat every anchor as `no_match`.
    Conflating "the pipeline broke" with "we searched and found nothing" is
    exactly the failure mode plan §4.3 calls out as unacceptable.
    """


async def generate_cfis(
    epub_path: str,
    anchors: List[CfiAnchor],
    on_ambiguous: OnAmbiguous = "error",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    node_bin: Optional[str] = None,
) -> List[CfiResult]:
    """Runs `cfi_batch.mjs` once against the full `anchors` batch for
    `epub_path` and returns per-anchor results, same length/order as
    `anchors`. Raises `CfiBatchError` on any whole-book failure.
    """
    if not anchors:
        return []
    if len(anchors) > MAX_ANCHORS:
        raise CfiBatchError(f"too many anchors: {len(anchors)} > {MAX_ANCHORS}")
    request = {"epubPath": epub_path, "onAmbiguous": on_ambiguous, "anchors": anchors}
    return await _run_batch(epub_path, request, len(anchors), timeout, node_bin)


async def convert_xpointers(
    epub_path: str,
    xpointers: List[dict],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    node_bin: Optional[str] = None,
) -> List[CfiResult]:
    """Converts KOReader xpointers to epubcfi strings via the same Node
    subprocess. Each item must contain `id` and `xpointer`.
    """
    if not xpointers:
        return []
    if len(xpointers) > MAX_ANCHORS:
        raise CfiBatchError(f"too many xpointers: {len(xpointers)} > {MAX_ANCHORS}")
    request = {"epubPath": epub_path, "xpointers": xpointers}
    return await _run_batch(epub_path, request, len(xpointers), timeout, node_bin)


async def _run_batch(
    epub_path: str,
    request_obj: dict,
    expected_len: int,
    timeout: float,
    node_bin: Optional[str],
) -> List[CfiResult]:
    request = json.dumps(request_obj, ensure_ascii=False).encode("utf-8")

    try:
        proc = await asyncio.create_subprocess_exec(
            node_bin or "node",
            NODE_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise CfiBatchError(f"node executable not found ({e})") from e

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(request), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise CfiBatchError(f"cfi_batch.mjs timed out after {timeout}s for {epub_path}")

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", "replace").strip()
        logging.error("[cfi_gen] cfi_batch.mjs failed (exit %s) for %s: %s", proc.returncode, epub_path, stderr_text)
        raise CfiBatchError(stderr_text or f"cfi_batch.mjs exited with code {proc.returncode}")

    if stderr:
        # A zero exit code with non-empty stderr still counts as a failure —
        # deliberately conservative per plan §4.3, so a warning printed by a
        # dependency (e.g. jsdom) doesn't silently pass as success.
        stderr_text = stderr.decode("utf-8", "replace").strip()
        logging.error("[cfi_gen] cfi_batch.mjs wrote to stderr (exit 0) for %s: %s", epub_path, stderr_text)
        raise CfiBatchError(stderr_text)

    try:
        response = json.loads(stdout.decode("utf-8"))
    except ValueError as e:
        raise CfiBatchError(f"cfi_batch.mjs produced invalid JSON: {e}") from e

    results = response.get("results")
    if not isinstance(results, list) or len(results) != expected_len:
        raise CfiBatchError("cfi_batch.mjs returned a malformed/mismatched result list")

    meta = response.get("meta") or {}
    if meta.get("sectionParseErrors"):
        logging.warning(
            "[cfi_gen] %s spine section(s) failed to parse for %s "
            "(anchors that could only have matched there will look like no_match)",
            meta["sectionParseErrors"],
            epub_path,
        )

    return results
