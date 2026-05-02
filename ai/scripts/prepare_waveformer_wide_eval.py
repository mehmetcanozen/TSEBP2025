"""Prepare a wide, reproducible Waveformer demo/evaluation audio set.

The script downloads public datasets, selects a small deterministic source set,
normalizes clips with FFmpeg, and renders curated mixtures for product demos.
It is intentionally command-line driven because the downloads are large and
should be started by the operator, not by an import or test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOAD_ROOT = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestdownloads"
DEFAULT_SOURCE_ROOT = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestsources"
DEFAULT_MIX_ROOT = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestmixed"

ESC50_URL = "https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip"
FSDK_AUDIO_TRAIN_URL = (
    "https://zenodo.org/records/2552860/files/FSDKaggle2018.audio_train.zip?download=1"
)
FSDK_AUDIO_TEST_URL = (
    "https://zenodo.org/records/2552860/files/FSDKaggle2018.audio_test.zip?download=1"
)
FSDK_META_URL = "https://zenodo.org/records/2552860/files/FSDKaggle2018.meta.zip?download=1"
FSDK_DOC_URL = "https://zenodo.org/records/2552860/files/FSDKaggle2018.doc.zip?download=1"
LIBRISPEECH_DEV_CLEAN_URL = "https://www.openslr.org/resources/12/dev-clean.tar.gz"

DOWNLOADS = (
    ("esc50-master.zip", ESC50_URL, "zip", "esc50"),
    ("FSDKaggle2018.audio_train.zip", FSDK_AUDIO_TRAIN_URL, "zip", "fsdkaggle2018"),
    ("FSDKaggle2018.audio_test.zip", FSDK_AUDIO_TEST_URL, "zip", "fsdkaggle2018"),
    ("FSDKaggle2018.meta.zip", FSDK_META_URL, "zip", "fsdkaggle2018"),
    ("FSDKaggle2018.doc.zip", FSDK_DOC_URL, "zip", "fsdkaggle2018"),
    ("librispeech-dev-clean.tar.gz", LIBRISPEECH_DEV_CLEAN_URL, "tar.gz", "librispeech"),
)

WAVEFORMER_20_TARGETS = (
    "alarm_clock",
    "baby_cry",
    "birds_chirping",
    "cat",
    "car_horn",
    "cock_a_doodle_doo",
    "cricket",
    "computer_typing",
    "dog",
    "glass_breaking",
    "gunshot",
    "music",
    "ocean",
    "door_knock",
    "siren",
    "speech",
    "thunderstorm",
    "toilet_flush",
)

SOURCE_ONLY_CLASSES = (
    "engine",
    "train",
    "airplane",
    "helicopter",
    "rain",
    "wind",
    "water_drops",
    "pouring_water",
    "footsteps",
    "coughing",
    "laughing",
    "clapping",
    "vacuum_cleaner",
    "washing_machine",
    "clock_tick",
    "chainsaw",
    "hand_saw",
    "church_bells",
    "bus",
    "keys_jangling",
)


@dataclass(frozen=True)
class SourceSpec:
    dataset: str
    label: str


@dataclass(frozen=True)
class Candidate:
    class_id: str
    dataset: str
    original_label: str
    path: Path
    source_id: str
    split: str
    license: str
    citation_source: str


@dataclass(frozen=True)
class DatasetPaths:
    esc50_root: Path
    fsdk_root: Path
    librispeech_dev_clean: Path


@dataclass(frozen=True)
class MixRecipe:
    name: str
    target: str
    sources: tuple[str, ...]
    story: str


SOURCE_CLASS_SPECS: dict[str, tuple[SourceSpec, ...]] = {
    "alarm_clock": (SourceSpec("esc50", "clock_alarm"),),
    "baby_cry": (SourceSpec("esc50", "crying_baby"),),
    "birds_chirping": (SourceSpec("esc50", "chirping_birds"),),
    "cat": (SourceSpec("esc50", "cat"), SourceSpec("fsdkaggle2018", "Meow")),
    "car_horn": (SourceSpec("esc50", "car_horn"),),
    "cock_a_doodle_doo": (SourceSpec("esc50", "rooster"),),
    "cricket": (SourceSpec("esc50", "crickets"),),
    "computer_typing": (
        SourceSpec("esc50", "keyboard_typing"),
        SourceSpec("fsdkaggle2018", "Computer_keyboard"),
    ),
    "dog": (SourceSpec("esc50", "dog"), SourceSpec("fsdkaggle2018", "Bark")),
    "glass_breaking": (
        SourceSpec("esc50", "glass_breaking"),
        SourceSpec("fsdkaggle2018", "Shatter"),
    ),
    "gunshot": (SourceSpec("fsdkaggle2018", "Gunshot_or_gunfire"),),
    "music": (
        SourceSpec("fsdkaggle2018", "Acoustic_guitar"),
        SourceSpec("fsdkaggle2018", "Electric_piano"),
        SourceSpec("fsdkaggle2018", "Violin_or_fiddle"),
        SourceSpec("fsdkaggle2018", "Saxophone"),
    ),
    "ocean": (SourceSpec("esc50", "sea_waves"),),
    "door_knock": (
        SourceSpec("esc50", "door_wood_knock"),
        SourceSpec("fsdkaggle2018", "Knock"),
    ),
    "siren": (SourceSpec("esc50", "siren"),),
    "speech": (SourceSpec("librispeech", "dev-clean"),),
    "thunderstorm": (SourceSpec("esc50", "thunderstorm"),),
    "toilet_flush": (SourceSpec("esc50", "toilet_flush"),),
    "engine": (SourceSpec("esc50", "engine"),),
    "train": (SourceSpec("esc50", "train"),),
    "airplane": (SourceSpec("esc50", "airplane"),),
    "helicopter": (SourceSpec("esc50", "helicopter"),),
    "rain": (SourceSpec("esc50", "rain"),),
    "wind": (SourceSpec("esc50", "wind"),),
    "water_drops": (SourceSpec("esc50", "water_drops"),),
    "pouring_water": (SourceSpec("esc50", "pouring_water"),),
    "footsteps": (SourceSpec("esc50", "footsteps"),),
    "coughing": (SourceSpec("esc50", "coughing"), SourceSpec("fsdkaggle2018", "Cough")),
    "laughing": (SourceSpec("esc50", "laughing"), SourceSpec("fsdkaggle2018", "Laughter")),
    "clapping": (SourceSpec("esc50", "clapping"), SourceSpec("fsdkaggle2018", "Applause")),
    "vacuum_cleaner": (SourceSpec("esc50", "vacuum_cleaner"),),
    "washing_machine": (SourceSpec("esc50", "washing_machine"),),
    "clock_tick": (SourceSpec("esc50", "clock_tick"),),
    "chainsaw": (SourceSpec("esc50", "chainsaw"),),
    "hand_saw": (SourceSpec("esc50", "hand_saw"),),
    "church_bells": (SourceSpec("esc50", "church_bells"), SourceSpec("fsdkaggle2018", "Chime")),
    "bus": (SourceSpec("fsdkaggle2018", "Bus"),),
    "keys_jangling": (SourceSpec("fsdkaggle2018", "Keys_jangling"),),
}

MIX_RECIPES: tuple[MixRecipe, ...] = (
    MixRecipe("dog_engine_car_diagnosis", "dog", ("dog", "engine"), "Record a car noise while a dog keeps barking."),
    MixRecipe("keyboard_speech_meeting", "computer_typing", ("computer_typing", "speech"), "Clean a meeting recording with loud keyboard typing."),
    MixRecipe("baby_cry_music_home", "baby_cry", ("baby_cry", "music"), "Keep music while suppressing a crying baby sample."),
    MixRecipe("siren_speech_street", "siren", ("siren", "speech"), "Record speech near a street siren."),
    MixRecipe("toilet_flush_podcast", "toilet_flush", ("toilet_flush", "speech"), "Remove a bathroom flush from a voice recording."),
    MixRecipe("door_knock_baby_sleep", "door_knock", ("door_knock", "baby_cry"), "Suppress door knocks during a baby monitor clip."),
    MixRecipe("car_horn_phone_call", "car_horn", ("car_horn", "speech"), "Clean a voice note with nearby car horns."),
    MixRecipe("cat_video_music", "cat", ("cat", "music"), "Remove cat sounds from a music-backed video."),
    MixRecipe("glass_breaking_party_music", "glass_breaking", ("glass_breaking", "music"), "Suppress glass break sounds at a party."),
    MixRecipe("thunderstorm_remote_call", "thunderstorm", ("thunderstorm", "speech"), "Clean a call during thunder."),
    MixRecipe("birds_window_meeting", "birds_chirping", ("birds_chirping", "speech"), "Suppress birds through an open window during a meeting."),
    MixRecipe("cricket_camping_speech", "cricket", ("cricket", "speech"), "Clean a campsite voice memo with crickets."),
    MixRecipe("ocean_voice_note", "ocean", ("ocean", "speech"), "Suppress waves in a seaside voice note."),
    MixRecipe("alarm_clock_sleepy_call", "alarm_clock", ("alarm_clock", "speech"), "Remove an alarm clock from a morning call."),
    MixRecipe("rooster_morning_music", "cock_a_doodle_doo", ("cock_a_doodle_doo", "music"), "Clean a morning clip with rooster noise."),
    MixRecipe("gunshot_news_speech", "gunshot", ("gunshot", "speech"), "Suppress sharp gunshot-like transients in speech."),
    MixRecipe("dog_train_station", "dog", ("dog", "train"), "Remove barking from a train-station recording."),
    MixRecipe("keyboard_footsteps_office", "computer_typing", ("computer_typing", "footsteps"), "Suppress typing while people walk near the desk."),
    MixRecipe("siren_music_stream", "siren", ("siren", "music"), "Clean a music stream polluted by sirens."),
    MixRecipe("car_horn_engine_check", "car_horn", ("car_horn", "engine"), "Suppress horns while inspecting engine noise."),
    MixRecipe("glass_breaking_speech_report", "glass_breaking", ("glass_breaking", "speech"), "Remove glass break noise from a spoken report."),
    MixRecipe("toilet_flush_music_recording", "toilet_flush", ("toilet_flush", "music"), "Clean a casual music recording with a flush interruption."),
    MixRecipe("birds_ocean_trip", "birds_chirping", ("birds_chirping", "ocean"), "Suppress birds while keeping beach ambience."),
    MixRecipe("cat_speech_vet_call", "cat", ("cat", "speech"), "Remove cat sounds during a vet phone call."),
    MixRecipe("alarm_water_drops_call", "alarm_clock", ("alarm_clock", "water_drops"), "Suppress an alarm clock while keeping small water sounds."),
    MixRecipe("car_horn_speech_traffic", "car_horn", ("car_horn", "speech", "engine"), "Clean street speech with horn and engine noise."),
    MixRecipe("door_knock_baby_sleep_rain", "door_knock", ("door_knock", "baby_cry", "rain"), "Suppress knocks during a rainy baby-room recording."),
    MixRecipe("glass_breaking_music_party_clap", "glass_breaking", ("glass_breaking", "music", "clapping"), "Suppress glass break noise in party audio."),
    MixRecipe("birds_speech_window_wind", "birds_chirping", ("birds_chirping", "speech", "wind"), "Clean a windy open-window meeting."),
    MixRecipe("thunderstorm_speech_call_rain", "thunderstorm", ("thunderstorm", "speech", "rain"), "Suppress thunder while rain and speech remain."),
    MixRecipe("dog_speech_engine_driveway", "dog", ("dog", "speech", "engine"), "Clean a driveway voice note while a dog barks."),
    MixRecipe("keyboard_speech_office_clock", "computer_typing", ("computer_typing", "speech", "clock_tick"), "Suppress typing in an office call."),
    MixRecipe("siren_speech_car_horn", "siren", ("siren", "speech", "car_horn"), "Suppress siren while retaining speech and horn context."),
    MixRecipe("toilet_flush_speech_water", "toilet_flush", ("toilet_flush", "speech", "pouring_water"), "Remove flush noise from a water-heavy indoor recording."),
    MixRecipe("cricket_speech_camping_wind", "cricket", ("cricket", "speech", "wind"), "Suppress crickets in a windy camping message."),
    MixRecipe("ocean_speech_airplane", "ocean", ("ocean", "speech", "airplane"), "Suppress ocean noise in a travel clip near aircraft."),
    MixRecipe("baby_cry_speech_washing_machine", "baby_cry", ("baby_cry", "speech", "washing_machine"), "Suppress baby cry while speech and laundry noise remain."),
    MixRecipe("cat_speech_laughing", "cat", ("cat", "speech", "laughing"), "Suppress cat sounds during a lively call."),
    MixRecipe("gunshot_speech_chainsaw", "gunshot", ("gunshot", "speech", "chainsaw"), "Suppress a sharp transient under speech and saw noise."),
    MixRecipe("rooster_speech_church", "cock_a_doodle_doo", ("cock_a_doodle_doo", "speech", "church_bells"), "Suppress rooster sound in a morning town clip."),
    MixRecipe("dog_engine_speech_carhorn", "dog", ("dog", "engine", "speech", "car_horn"), "Record car diagnosis while dog and horn noise intrude."),
    MixRecipe("keyboard_speech_music_alarm", "computer_typing", ("computer_typing", "speech", "music", "alarm_clock"), "Suppress typing in a noisy desk recording."),
    MixRecipe("baby_cry_vacuum_speech_door", "baby_cry", ("baby_cry", "vacuum_cleaner", "speech", "door_knock"), "Suppress baby cry in a busy home recording."),
    MixRecipe("siren_speech_engine_rain", "siren", ("siren", "speech", "engine", "rain"), "Clean rainy roadside speech by removing siren."),
    MixRecipe("glass_breaking_clap_music_speech", "glass_breaking", ("glass_breaking", "clapping", "music", "speech"), "Remove glass break from a party speech clip."),
    MixRecipe("birds_ocean_speech_wind", "birds_chirping", ("birds_chirping", "ocean", "speech", "wind"), "Suppress birds in a beach interview."),
    MixRecipe("thunderstorm_rain_speech_coughing", "thunderstorm", ("thunderstorm", "rain", "speech", "coughing"), "Remove thunder from a rainy cough-and-speech recording."),
    MixRecipe("toilet_flush_water_speech_clock", "toilet_flush", ("toilet_flush", "pouring_water", "speech", "clock_tick"), "Suppress flush noise in an indoor voice memo."),
    MixRecipe("car_horn_bus_speech_keys", "car_horn", ("car_horn", "bus", "speech", "keys_jangling"), "Remove car horn from bus-stop voice audio."),
    MixRecipe("gunshot_hand_saw_speech_siren", "gunshot", ("gunshot", "hand_saw", "speech", "siren"), "Suppress sharp gunshot-like events around tools and sirens."),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download, normalize, and mix the Waveformer wide demo dataset.",
    )
    parser.add_argument("--download-root", type=Path, default=DEFAULT_DOWNLOAD_ROOT)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--mix-root", type=Path, default=DEFAULT_MIX_ROOT)
    parser.add_argument("--clips-per-source", type=int, default=2)
    parser.add_argument("--mix-count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--skip-downloads",
        action="store_true",
        help="Use already downloaded/extracted dataset files only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the static recipe and print the planned work without downloading or writing files.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip ffprobe validation after rendering WAV files.",
    )
    return parser


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._-") or "item"


def validate_static_config(mix_count: int, clips_per_source: int) -> None:
    if clips_per_source < 2:
        raise SystemExit("--clips-per-source must be at least 2.")
    if not 1 <= mix_count <= len(MIX_RECIPES):
        raise SystemExit(f"--mix-count must be between 1 and {len(MIX_RECIPES)}.")
    if len(MIX_RECIPES) != 50:
        raise SystemExit(f"Expected 50 static mix recipes, found {len(MIX_RECIPES)}.")

    full_counts = {2: 0, 3: 0, 4: 0}
    for recipe in MIX_RECIPES:
        if recipe.target not in WAVEFORMER_20_TARGETS:
            raise SystemExit(f"Recipe {recipe.name} uses unknown target {recipe.target}.")
        if recipe.target not in recipe.sources:
            raise SystemExit(f"Recipe {recipe.name} must include its target source.")
        if len(recipe.sources) not in full_counts:
            raise SystemExit(f"Recipe {recipe.name} has unsupported source count.")
        full_counts[len(recipe.sources)] += 1
        for class_id in recipe.sources:
            if class_id not in SOURCE_CLASS_SPECS:
                raise SystemExit(f"Recipe {recipe.name} references unmapped source {class_id}.")
    if full_counts != {2: 25, 3: 15, 4: 10}:
        raise SystemExit(f"Expected 25/15/10 recipe split, found {full_counts}.")


def print_dry_run(args: argparse.Namespace) -> None:
    planned = MIX_RECIPES[: args.mix_count]
    counts: dict[int, int] = {}
    for recipe in planned:
        counts[len(recipe.sources)] = counts.get(len(recipe.sources), 0) + 1
    required_classes = sorted({source for recipe in planned for source in recipe.sources})
    print("Waveformer wide eval dry run")
    print(f"  downloads: {args.download_root.resolve()}")
    print(f"  sources:   {args.source_root.resolve()}")
    print(f"  mixes:     {args.mix_root.resolve()}")
    print(f"  recipes:   {len(planned)} ({counts})")
    print(f"  classes:   {len(required_classes)}")
    print("  download URLs:")
    for filename, url, _, _ in DOWNLOADS:
        print(f"    {filename}: {url}")
    print("  first recipes:")
    for index, recipe in enumerate(planned[:10], start=1):
        print(
            f"    {index:03d}: target={recipe.target} "
            f"sources={'+'.join(recipe.sources)} name={recipe.name}"
        )


def require_tool(executable: str) -> None:
    if shutil.which(executable) is None:
        raise SystemExit(f"Required executable not found on PATH: {executable}")
    subprocess.run(
        [executable, "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def download_file(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"cached: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"downloading: {url}")
    with urllib.request.urlopen(url) as response, temporary.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        copied = 0
        next_report = 64 * 1024 * 1024
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            copied += len(chunk)
            if copied >= next_report:
                if total:
                    print(f"  {copied / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB")
                else:
                    print(f"  {copied / 1024 / 1024:.0f} MB")
                next_report += 64 * 1024 * 1024
    temporary.replace(destination)


def ensure_safe_member(base: Path, name: str) -> None:
    target = (base / name).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise RuntimeError(f"Archive member escapes extraction root: {name}")


def extract_archive(archive: Path, destination: Path, archive_kind: str, marker_name: str) -> None:
    marker = destination / f".extracted_{marker_name}"
    if marker.exists():
        print(f"extracted: {archive.name}")
        return
    destination.mkdir(parents=True, exist_ok=True)
    print(f"extracting: {archive.name}")
    if archive_kind == "zip":
        with zipfile.ZipFile(archive) as zip_handle:
            for member in zip_handle.namelist():
                ensure_safe_member(destination, member)
            zip_handle.extractall(destination)
    elif archive_kind == "tar.gz":
        with tarfile.open(archive, "r:gz") as tar_handle:
            for member in tar_handle.getmembers():
                ensure_safe_member(destination, member.name)
            tar_handle.extractall(destination)
    else:
        raise ValueError(f"Unsupported archive kind: {archive_kind}")
    marker.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")


def prepare_datasets(download_root: Path, skip_downloads: bool) -> DatasetPaths:
    archive_root = download_root / "archives"
    extract_root = download_root / "extracted"
    for filename, url, archive_kind, extract_group in DOWNLOADS:
        archive_path = archive_root / filename
        if not skip_downloads:
            download_file(url, archive_path)
        if not archive_path.exists():
            raise SystemExit(f"Missing archive {archive_path}. Rerun without --skip-downloads.")
        extract_destination = extract_root / extract_group
        extract_archive(archive_path, extract_destination, archive_kind, safe_name(filename))

    esc_candidates = sorted((extract_root / "esc50").glob("ESC-50-*"))
    esc_root = esc_candidates[0] if esc_candidates else extract_root / "esc50" / "ESC-50-master"
    fsdk_root = extract_root / "fsdkaggle2018"
    librispeech_root = extract_root / "librispeech" / "LibriSpeech" / "dev-clean"
    paths = DatasetPaths(
        esc50_root=esc_root,
        fsdk_root=fsdk_root,
        librispeech_dev_clean=librispeech_root,
    )
    assert_dataset_paths(paths)
    return paths


def assert_dataset_paths(paths: DatasetPaths) -> None:
    required = (
        paths.esc50_root / "meta" / "esc50.csv",
        paths.esc50_root / "audio",
        paths.fsdk_root / "FSDKaggle2018.meta",
        paths.fsdk_root / "FSDKaggle2018.audio_train",
        paths.fsdk_root / "FSDKaggle2018.audio_test",
        paths.librispeech_dev_clean,
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        joined = "\n  ".join(str(path) for path in missing)
        raise SystemExit(f"Dataset extraction looks incomplete:\n  {joined}")


def reverse_source_specs() -> dict[tuple[str, str], list[str]]:
    reverse: dict[tuple[str, str], list[str]] = {}
    for class_id, specs in SOURCE_CLASS_SPECS.items():
        for spec in specs:
            reverse.setdefault((spec.dataset, spec.label), []).append(class_id)
    return reverse


def collect_candidates(paths: DatasetPaths) -> dict[str, list[Candidate]]:
    reverse = reverse_source_specs()
    candidates: dict[str, list[Candidate]] = {class_id: [] for class_id in SOURCE_CLASS_SPECS}
    collect_esc50(paths, reverse, candidates)
    collect_fsdk(paths, reverse, candidates)
    collect_librispeech(paths, reverse, candidates)
    return candidates


def collect_esc50(
    paths: DatasetPaths,
    reverse: dict[tuple[str, str], list[str]],
    candidates: dict[str, list[Candidate]],
) -> None:
    meta_path = paths.esc50_root / "meta" / "esc50.csv"
    with meta_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row["category"]
            class_ids = reverse.get(("esc50", label), [])
            if not class_ids:
                continue
            audio_path = paths.esc50_root / "audio" / row["filename"]
            if not audio_path.exists():
                continue
            license_name = "CC-BY-3.0" if row.get("esc10") == "True" else "CC-BY-NC-3.0"
            for class_id in class_ids:
                candidates[class_id].append(
                    Candidate(
                        class_id=class_id,
                        dataset="esc50",
                        original_label=label,
                        path=audio_path,
                        source_id=row.get("src_file") or row.get("clip_id") or audio_path.stem,
                        split=f"fold_{row.get('fold', '')}",
                        license=license_name,
                        citation_source="ESC-50 / Karol J. Piczak",
                    )
                )


def collect_fsdk(
    paths: DatasetPaths,
    reverse: dict[tuple[str, str], list[str]],
    candidates: dict[str, list[Candidate]],
) -> None:
    splits = (
        (
            paths.fsdk_root / "FSDKaggle2018.meta" / "train_post_competition.csv",
            paths.fsdk_root / "FSDKaggle2018.audio_train",
            "train",
        ),
        (
            paths.fsdk_root / "FSDKaggle2018.meta" / "test_post_competition_scoring_clips.csv",
            paths.fsdk_root / "FSDKaggle2018.audio_test",
            "test",
        ),
    )
    for meta_path, audio_root, split in splits:
        with meta_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                label = row["label"]
                class_ids = reverse.get(("fsdkaggle2018", label), [])
                if not class_ids:
                    continue
                audio_path = audio_root / row["fname"]
                if not audio_path.exists():
                    continue
                quality = "verified" if row.get("manually_verified") == "1" else "unverified"
                for class_id in class_ids:
                    candidates[class_id].append(
                        Candidate(
                            class_id=class_id,
                            dataset="fsdkaggle2018",
                            original_label=label,
                            path=audio_path,
                            source_id=row.get("freesound_id") or audio_path.stem,
                            split=f"{split}_{quality}",
                            license=row.get("license") or "per-clip Freesound Creative Commons",
                            citation_source="FSDKaggle2018 / DCASE 2018 Task 2",
                        )
                    )


def collect_librispeech(
    paths: DatasetPaths,
    reverse: dict[tuple[str, str], list[str]],
    candidates: dict[str, list[Candidate]],
) -> None:
    class_ids = reverse.get(("librispeech", "dev-clean"), [])
    if not class_ids:
        return
    for audio_path in sorted(paths.librispeech_dev_clean.glob("*/*/*.flac")):
        for class_id in class_ids:
            candidates[class_id].append(
                Candidate(
                    class_id=class_id,
                    dataset="librispeech",
                    original_label="speech",
                    path=audio_path,
                    source_id=audio_path.stem,
                    split="dev-clean",
                    license="CC-BY-4.0",
                    citation_source="LibriSpeech ASR corpus / OpenSLR SLR12",
                )
            )


def stable_rng(seed: int, key: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def select_sources(
    candidates: dict[str, list[Candidate]],
    required_classes: Iterable[str],
    clips_per_source: int,
    seed: int,
) -> dict[str, list[Candidate]]:
    selected: dict[str, list[Candidate]] = {}
    for class_id in sorted(required_classes):
        class_candidates = sorted(
            candidates.get(class_id, []),
            key=lambda row: (row.dataset, row.original_label, str(row.path)),
        )
        if len(class_candidates) < clips_per_source:
            raise SystemExit(
                f"Class {class_id} has {len(class_candidates)} candidates, "
                f"need {clips_per_source}. Check dataset extraction/mapping."
            )
        shuffled = list(class_candidates)
        stable_rng(seed, class_id).shuffle(shuffled)
        selected[class_id] = shuffled[:clips_per_source]
    return selected


def run_command(command: Sequence[str]) -> None:
    subprocess.run(command, check=True)


def normalize_sources(
    selected: dict[str, list[Candidate]],
    source_root: Path,
    ffmpeg: str,
    ffprobe: str,
    validate: bool,
) -> tuple[dict[str, list[Path]], list[dict[str, str]]]:
    source_root.mkdir(parents=True, exist_ok=True)
    normalized: dict[str, list[Path]] = {}
    rows: list[dict[str, str]] = []
    for class_id, candidates in sorted(selected.items()):
        normalized[class_id] = []
        for index, candidate in enumerate(candidates, start=1):
            output_path = source_root / (
                f"{class_id}__{index:02d}__{candidate.dataset}__"
                f"{safe_name(candidate.source_id or candidate.path.stem)}.wav"
            )
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(candidate.path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-af",
                (
                    "apad=pad_dur=5,atrim=0:5,"
                    "loudnorm=I=-18:TP=-1.5:LRA=11,"
                    "afade=t=in:st=0:d=0.03,afade=t=out:st=4.95:d=0.05"
                ),
                "-sample_fmt",
                "s16",
                str(output_path),
            ]
            print(f"source {class_id} #{index}: {output_path.name}")
            run_command(command)
            if validate:
                validate_wave(output_path, ffprobe)
            normalized[class_id].append(output_path)
            rows.append(
                {
                    "class_id": class_id,
                    "clip_index": str(index),
                    "normalized_path": str(output_path),
                    "dataset": candidate.dataset,
                    "original_label": candidate.original_label,
                    "original_path": str(candidate.path),
                    "source_id": candidate.source_id,
                    "split": candidate.split,
                    "license": candidate.license,
                    "citation_source": candidate.citation_source,
                }
            )
    write_csv(source_root / "source_manifest.csv", rows)
    return normalized, rows


def build_mix_filter(source_count: int) -> str:
    delays = (0, 450, 875, 1250)
    volumes = (1.0, 0.78, 0.70, 0.62)
    parts = []
    labels = []
    for index in range(source_count):
        labels.append(f"[a{index}]")
        if delays[index]:
            parts.append(
                f"[{index}:a]adelay={delays[index]}:all=1,"
                f"volume={volumes[index]:.2f}[a{index}]"
            )
        else:
            parts.append(f"[{index}:a]volume={volumes[index]:.2f}[a{index}]")
    parts.append(
        "".join(labels)
        + f"amix=inputs={source_count}:duration=longest:normalize=0,"
        "alimiter=limit=0.95,loudnorm=I=-18:TP=-1.5:LRA=11,"
        "atrim=0:5,asetpts=N/SR/TB[out]"
    )
    return ";".join(parts)


def render_mixes(
    recipes: Sequence[MixRecipe],
    normalized: dict[str, list[Path]],
    mix_root: Path,
    ffmpeg: str,
    ffprobe: str,
    validate: bool,
) -> list[dict[str, str]]:
    mix_root.mkdir(parents=True, exist_ok=True)
    use_counts = {class_id: 0 for class_id in normalized}
    rows: list[dict[str, str]] = []
    for mix_index, recipe in enumerate(recipes, start=1):
        input_paths = []
        for class_id in recipe.sources:
            available = normalized[class_id]
            selected = available[use_counts[class_id] % len(available)]
            use_counts[class_id] += 1
            input_paths.append(selected)
        mix_stem = f"mix_{mix_index:03d}_target_{recipe.target}_{'_'.join(recipe.sources)}"
        output_path = mix_root / f"{safe_name(mix_stem)}.wav"
        command = [ffmpeg, "-y"]
        for input_path in input_paths:
            command.extend(["-i", str(input_path)])
        command.extend(
            [
                "-filter_complex",
                build_mix_filter(len(input_paths)),
                "-map",
                "[out]",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-sample_fmt",
                "s16",
                str(output_path),
            ]
        )
        print(f"mix {mix_index:03d}: {output_path.name}")
        run_command(command)
        if validate:
            validate_wave(output_path, ffprobe)
        rows.append(
            {
                "mix_index": str(mix_index),
                "mix_name": recipe.name,
                "target": recipe.target,
                "output_path": str(output_path),
                "sound_count": str(len(recipe.sources)),
                "source_classes": "+".join(recipe.sources),
                "source_files": "|".join(str(path) for path in input_paths),
                "story": recipe.story,
                "suppression_hint": (
                    f"Suppress target '{recipe.target}' from {output_path.name}"
                ),
            }
        )
    write_csv(mix_root / "mix_manifest.csv", rows)
    return rows


def validate_wave(path: Path, ffprobe: str) -> None:
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels,sample_fmt",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError(f"No audio stream found in {path}")
    stream = streams[0]
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)
    sample_fmt = stream.get("sample_fmt")
    if sample_rate != 44100 or channels != 1 or sample_fmt != "s16":
        raise RuntimeError(
            f"{path} is not 44.1 kHz mono s16 WAV: "
            f"sample_rate={sample_rate}, channels={channels}, sample_fmt={sample_fmt}"
        )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows to write for {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote: {path}")


def write_dataset_sources(download_root: Path, source_root: Path, mix_root: Path) -> None:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_surface": "waveformer20",
        "download_root": str(download_root),
        "source_root": str(source_root),
        "mix_root": str(mix_root),
        "sources": [
            {
                "name": "ESC-50",
                "url": ESC50_URL,
                "notes": "Environmental sounds, CC-BY-NC-3.0 overall; ESC-10 subset CC-BY.",
            },
            {
                "name": "FSDKaggle2018",
                "url": "https://zenodo.org/records/2552860",
                "notes": "Freesound clips with per-clip Creative Commons licenses.",
            },
            {
                "name": "LibriSpeech dev-clean",
                "url": LIBRISPEECH_DEV_CLEAN_URL,
                "notes": "Clean read speech, CC-BY-4.0.",
            },
        ],
        "excluded_current_waveformer_labels": ["hammer", "singing"],
    }
    path = mix_root / "dataset_sources.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_static_config(args.mix_count, args.clips_per_source)
    require_tool(args.ffmpeg)
    require_tool(args.ffprobe)

    if args.dry_run:
        print_dry_run(args)
        return 0

    recipes = MIX_RECIPES[: args.mix_count]
    required_classes = {source for recipe in recipes for source in recipe.sources}
    paths = prepare_datasets(args.download_root.resolve(), args.skip_downloads)
    candidates = collect_candidates(paths)
    selected = select_sources(
        candidates,
        required_classes=required_classes,
        clips_per_source=args.clips_per_source,
        seed=args.seed,
    )
    normalized, source_rows = normalize_sources(
        selected,
        args.source_root.resolve(),
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        validate=not args.no_validate,
    )
    mix_rows = render_mixes(
        recipes,
        normalized,
        args.mix_root.resolve(),
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        validate=not args.no_validate,
    )
    write_dataset_sources(args.download_root.resolve(), args.source_root.resolve(), args.mix_root.resolve())
    print(
        f"Done. Wrote {len(source_rows)} normalized sources and {len(mix_rows)} mixes "
        f"to {args.mix_root.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
