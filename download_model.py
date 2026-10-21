"""Download the exact timestamp-capable Paraformer variant; never execute remote code."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path

MODEL_ID = "sherpa-onnx-paraformer-zh-2023-09-14"
BASE = f"https://huggingface.co/csukuangfj/{MODEL_ID}/resolve/main"


def download_model(directory, progress=lambda message, percent: None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name in ("tokens.txt", "model.int8.onnx"):
        destination = directory / name
        if destination.is_file() and destination.stat().st_size > (1000000 if name.endswith("onnx") else 1000):
            progress(f"已找到 {name}", 100)
            continue
        part = destination.with_suffix(destination.suffix + ".part")
        progress(f"正在下载 {name}（首次使用需要联网）", 0)
        req = urllib.request.Request(f"{BASE}/{name}", headers={"User-Agent": "KouboCut-Beta/0.1"})
        with urllib.request.urlopen(req, timeout=90) as response, part.open("wb") as output:
            total = int(response.headers.get("Content-Length", 0))
            size, digest = 0, hashlib.sha256()
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
                output.write(chunk)
                progress(f"下载 {name}：{size / 1048576:.1f} MB", round(size / total * 100) if total else 0)
            if total and size != total:
                raise ValueError("模型下载不完整，请重试")
            manifest[name] = {"bytes": size, "sha256": digest.hexdigest()}
        os.replace(part, destination)
    (directory / "download-info.json").write_text(json.dumps({"model": MODEL_ID, "files": manifest}, indent=2), encoding="utf-8")
    return str(directory)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=str(Path(__file__).parent / "data" / "models" / MODEL_ID))
    args = parser.parse_args()
    last = [""]
    def report(message, percent):
        marker = message.split("：")[0] + str(percent // 10)
        if marker != last[0]:
            print(message, flush=True)
            last[0] = marker
    download_model(args.directory, report)
