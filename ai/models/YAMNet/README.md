# YAMNet

This directory holds the local YAMNet assets used by the semantic detection runtime.
These files used to live under `ai/models/checkpoints/`; they now live in a dedicated
model folder so Waveformer and YAMNet can be managed independently.

## Layout

- `saved_models/yamnet_1/` - extracted TensorFlow Hub SavedModel used by `SemanticDetective`
- `archives/yamnet_1.tar.gz` - original TF Hub archive for the SavedModel
- `archives/yamnet-tflite-classification-tflite-v1.tar.gz` - archived TFLite package
- `tflite/1.tflite` - extracted TFLite model
- `metadata/yamnet_class_map.csv` - local copy of the class map CSV

## Runtime Notes

- The runtime prefers `saved_models/yamnet_1/` when it is present.
- If the local SavedModel is missing, `SemanticDetective` falls back to
  `https://tfhub.dev/google/yamnet/1`.
- `python ai/scripts/setup/download_models.py` stores future YAMNet downloads in this folder.
