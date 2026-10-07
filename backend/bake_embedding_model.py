import json
import os
from pathlib import Path

from huggingface_hub import model_info, snapshot_download

model_name = os.environ["EMBEDDING_MODEL"]
model_path = Path(os.environ["EMBEDDING_CACHE_DIR"])
model = model_info(model_name)
model_version = model.sha
available_files = {file.rfilename for file in model.siblings}
weight_file = next(
    (
        name
        for name in ("model.safetensors", "pytorch_model.bin")
        if name in available_files
    ),
    None,
)
if weight_file is None:
    raise RuntimeError(f"No supported PyTorch weights found for {model_name!r}.")

snapshot_download(
    repo_id=model_name,
    revision=model_version,
    local_dir=str(model_path),
    allow_patterns=[
        weight_file,
        "1_Pooling/**",
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
)
(model_path / "model-metadata.json").write_text(
    json.dumps({"model_name": model_name, "model_version": model_version}),
    encoding="utf-8",
)
