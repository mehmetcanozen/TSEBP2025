"""Internal query-first planning/result types for CodecSep runtime."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from ai.ai_runtime.utils.codecsep import normalize_codecsep_prompt_map, normalize_codecsep_prompt_value


CodecSepSlot = Literal["speech", "music", "sfx"]
CodecSepMode = Literal["fixed_category", "compat", "audiocaps_native", "experimental_search", "auto", "query_first"]
CodecSepQueryStrategy = Literal["single_pass", "slot_search"]
CodecSepReconstructionPolicy = Literal["subtract_target", "keep_complement", "score_select", "wiener_mask"]


@dataclass(slots=True)
class CodecSepCandidateScore:
    """Reference-free score summary for one query candidate."""

    slot: CodecSepSlot
    target_score: float
    preserve_score: float
    mixture_score: float
    total_score: float
    strategy: str


@dataclass(slots=True)
class CodecSepQueryPlan:
    """Prompt-native plan for one CodecSep extraction/suppression query."""

    target_prompts: list[str]
    preferred_slot: CodecSepSlot
    target_label: str = ""
    negative_prompts: list[str] = field(default_factory=list)
    preserve_prompts: list[str] = field(default_factory=list)
    alternate_slots: list[CodecSepSlot] = field(default_factory=list)
    slot_prompt_overrides: dict[str, list[str]] = field(default_factory=dict)
    reconstruction_policy: CodecSepReconstructionPolicy = "subtract_target"
    query_strategy: CodecSepQueryStrategy = "single_pass"
    multistep_steps: int = 0
    aggressiveness: float = 1.0
    mode: CodecSepMode = "auto"
    use_multistep: bool = False
    debug_context: dict[str, object] = field(default_factory=dict)

    def normalized(self) -> "CodecSepQueryPlan":
        slot_overrides = normalize_codecsep_prompt_map(self.slot_prompt_overrides)
        return replace(
            self,
            target_prompts=self._normalize_prompts(self.target_prompts),
            negative_prompts=self._normalize_prompts(self.negative_prompts),
            preserve_prompts=self._normalize_prompts(self.preserve_prompts),
            alternate_slots=self._dedupe_slots(self.alternate_slots),
            slot_prompt_overrides={
                slot: self._normalize_prompts(prompt_values)
                for slot, prompt_values in slot_overrides.items()
            },
            multistep_steps=max(0, int(self.multistep_steps or 0)),
        )

    @staticmethod
    def _normalize_prompts(
        prompts: list[str] | tuple[str, ...] | str | None,
        *,
        max_prompts: int = 4,
    ) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for prompt in normalize_codecsep_prompt_value(prompts):
            key = prompt.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(prompt)
            if len(deduped) >= max_prompts:
                break
        return deduped

    @staticmethod
    def _dedupe_slots(slots: list[CodecSepSlot] | tuple[CodecSepSlot, ...]) -> list[CodecSepSlot]:
        deduped: list[CodecSepSlot] = []
        for slot in slots:
            if slot not in deduped:
                deduped.append(slot)
        return deduped

    def candidate_slots(self) -> list[CodecSepSlot]:
        slots: list[CodecSepSlot] = [self.preferred_slot]
        if self.query_strategy == "slot_search":
            for slot in self.alternate_slots:
                if slot not in slots:
                    slots.append(slot)
        return slots

    def cache_key(self) -> tuple:
        normalized = self.normalized()
        return (
            tuple(normalized.target_prompts),
            tuple(normalized.negative_prompts),
            tuple(normalized.preserve_prompts),
            normalized.preferred_slot,
            tuple(normalized.alternate_slots),
            normalized.reconstruction_policy,
            normalized.query_strategy,
            normalized.multistep_steps,
        )

    def force_slot(self, slot: CodecSepSlot) -> "CodecSepQueryPlan":
        return replace(
            self,
            preferred_slot=slot,
            alternate_slots=[],
            query_strategy="single_pass",
        )


@dataclass(slots=True)
class CodecSepQueryResult:
    """Result of a query-first CodecSep runtime call."""

    plan: CodecSepQueryPlan
    selected_slot: CodecSepSlot
    target_audio: object
    clean_audio: object
    raw_outputs: dict[str, object]
    normalized_outputs: dict[str, object]
    score: CodecSepCandidateScore
    candidate_scores: dict[str, CodecSepCandidateScore]
    chosen_policy: CodecSepReconstructionPolicy
    used_multistep: bool = False
