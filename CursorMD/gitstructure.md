# Git Structure Notes

- 2025-12-11 (after reviewer fixes)
  - Branch: `feature/devplan1-audio-mixer`
  - Recent commits:
    - Safety/doc updates: priority helper default HIGH with optional REALTIME flag; queue exception tightening; torchaudio shim note; channel layout doc; README expansion.
    - Tests: added WaveformerSeparator unit tests.
  - Tests run locally: `python -m pytest desktop/tests -q`
# Git Structure Notes

- 2025-12-11 (before commits)
  - Branch: `feature/devplan1-audio-mixer` (fresh from `master`)
  - Pending changes: README docs; training requirements; new Waveformer wrapper and desktop audio pipeline (audio I/O, ring buffer, gain smoother, multiprocessing process, controller, inference shim), CLI mixer test, unit tests, desktop requirements, progress log.

- 2025-12-11 (after commits)
  - Branch: `feature/devplan1-audio-mixer`
  - Commits:
    - `feat: add desktop audio mixer pipeline` — adds Waveformer inference wrapper, desktop audio stack (I/O, ring buffer, gain smoothing, multiprocessing process, controller, CLI smoke test), tests, and requirements updates.
    - `docs: add mixer docs and progress updates` — documents desktop mixer smoke test, records progress, and logs branch state.
