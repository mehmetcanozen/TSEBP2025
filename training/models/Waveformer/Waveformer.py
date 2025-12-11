import argparse
import os

import torch
import torchaudio
import wget
import soundfile as sf

# torchaudio 2.9 removes list_audio_backends; speechbrain expects it.
if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["sox_io"]

from src.helpers import utils
from src.training.dcc_tf import Net as Waveformer

TARGETS = [
    "Acoustic_guitar",
    "Applause",
    "Bark",
    "Bass_drum",
    "Burping_or_eructation",
    "Bus",
    "Cello",
    "Chime",
    "Clarinet",
    "Computer_keyboard",
    "Cough",
    "Cowbell",
    "Double_bass",
    "Drawer_open_or_close",
    "Electric_piano",
    "Fart",
    "Finger_snapping",
    "Fireworks",
    "Flute",
    "Glockenspiel",
    "Gong",
    "Gunshot_or_gunfire",
    "Harmonica",
    "Hi-hat",
    "Keys_jangling",
    "Knock",
    "Laughter",
    "Meow",
    "Microwave_oven",
    "Oboe",
    "Saxophone",
    "Scissors",
    "Shatter",
    "Snare_drum",
    "Squeak",
    "Tambourine",
    "Tearing",
    "Telephone",
    "Trumpet",
    "Violin_or_fiddle",
    "Writing",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input", type=str, default=None, help="Path to the input audio file."
    )
    parser.add_argument(
        "output",
        type=str,
        default=None,
        help="Path to the output audio file (output is written in the .wav format).",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        type=str,
        default=[],
        help="Targets to output. Pick a subset of: %s" % TARGETS,
    )
    args = parser.parse_args()

    if not os.path.exists("default_config.json"):
        config_url = "https://targetsound.cs.washington.edu/files/default_config.json"
        print("Downloading model configuration from %s:" % config_url)
        wget.download(config_url)

    if not os.path.exists("default_ckpt.pt"):
        ckpt_url = "https://targetsound.cs.washington.edu/files/default_ckpt.pt"
        print("\nDownloading the checkpoint from %s:" % ckpt_url)
        wget.download(ckpt_url)

    # Instantiate model
    params = utils.Params("default_config.json")
    model = Waveformer(**params.model_params)
    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    model.load_state_dict(
        torch.load(
            "default_ckpt.pt", map_location=device, weights_only=False
        )["model_state_dict"]
    )
    model.to(device).eval()

    # Read input audio (soundfile avoids torchcodec dependency on torchaudio 2.9)
    mixture_np, fs = sf.read(args.input, always_2d=True)
    mixture = torch.tensor(mixture_np.T, dtype=torch.float32)
    if fs != 44100:
        mixture = torchaudio.functional.resample(mixture, orig_freq=fs, new_freq=44100)
    mixture = mixture.unsqueeze(0).to(device)
    print("Loaded input audio from %s" % args.input)

    # Construct the query vector
    if len(args.targets) == 0:
        query = torch.ones(1, len(TARGETS))
    else:
        query = torch.zeros(1, len(TARGETS))
        for t in args.targets:
            query[0, TARGETS.index(t)] = 1.0

    with torch.inference_mode():
        output = model(mixture.to(device), query.to(device)).squeeze(0).cpu()
    if fs != 44100:
        output = torchaudio.functional.resample(output, orig_freq=44100, new_freq=fs)
    print("Inference done. Saving output audio to %s" % args.output)

    assert not os.path.exists(args.output), "Output file already exists."
    sf.write(args.output, output.transpose(0, 1).numpy(), fs)
