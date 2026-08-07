"""Translate an approved full-runtime concept into hidden provider-sized work."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping


def balanced_durations(total: int, minimum: int, maximum: int) -> tuple[int, ...]:
    total, minimum, maximum = int(total), int(minimum), int(maximum)
    if total < minimum:
        raise ValueError(f"Runtime must be at least {minimum} seconds.")
    count = (total + maximum - 1) // maximum
    if total < count * minimum:
        raise ValueError("Runtime cannot be represented by provider duration limits.")
    base, remainder = divmod(total, count)
    values = tuple(base + (1 if index < remainder else 0) for index in range(count))
    if any(value < minimum or value > maximum for value in values):
        raise ValueError("Planner produced an invalid provider segment.")
    return values


class VideoExecutionPlanner:
    schema_version = "video_execution_plan_v1"

    def plan(self, concept: Mapping, capability: Mapping, *, session_id: str, run_id: str, source_media_type: str = "image") -> dict:
        runtime = int(concept["requested_runtime"])
        durations = balanced_durations(runtime, int(capability["min_native_duration"]), int(capability["max_native_duration"]))
        timeline = concept["timeline"]
        cursor, segments = 0, []
        for ordinal, duration in enumerate(durations, 1):
            end = cursor + duration
            beats = [beat for beat in timeline if float(beat["end_second"]) > cursor and float(beat["start_second"]) < end]
            instruction = self._render_segment(concept, beats, cursor, end)
            digest = hashlib.sha256(json.dumps({"session": session_id, "run": run_id, "ordinal": ordinal,
                "prompt": instruction, "start": cursor, "end": end}, sort_keys=True).encode()).hexdigest()
            segments.append({"ordinal": ordinal, "generation_type": "image_to_video" if ordinal == 1 and source_media_type == "image" else "video_extend",
                "start_second": cursor, "end_second": end, "planned_duration": duration,
                "prompt": instruction, "dispatch_identity": digest})
            cursor = end
        return {"schema_version": self.schema_version, "requested_runtime": runtime,
                "provider_id": capability["provider_id"], "segments": segments}

    @staticmethod
    def _render_segment(concept, beats, start, end):
        directions = " ".join(str(beat.get("creative_beat") or beat.get("subject_direction") or "") for beat in beats)
        return (f"Continue one coherent video: {concept['experience_summary']} Segment {start}-{end}s. "
                f"{directions} Preserve identity, anatomy, wardrobe, lighting, environment, motion continuity and ending handoff.").strip()
