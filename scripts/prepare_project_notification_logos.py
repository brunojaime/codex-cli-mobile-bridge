#!/usr/bin/env python3
"""Prepare bounded PNG copies of reviewed project logos (Pillow/CairoSVG tool deps).

Reads only the explicitly listed image sources; never scans/copies project state.
The source map is JSON: {workspace_path: image_path}. Missing applications use the
supplied brand fallback, clearly marked in the catalog. No notification is sent.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from PIL import Image

    args.output.mkdir(parents=True, exist_ok=True)

    def convert(source, name):
        data = source.read_bytes()
        if source.suffix.lower() == ".svg":
            import cairosvg
            data = cairosvg.svg2png(bytestring=data, output_width=256, output_height=256)
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        image.thumbnail((256, 256))
        canvas = Image.new("RGBA", (256, 256))
        canvas.paste(image, ((256-image.width)//2, (256-image.height)//2))
        canvas.save(args.output / name, optimize=True)
        return {"asset": name, "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}

    fallback = convert(args.fallback.resolve(), "nienfos-fallback.png")
    catalog = {"version": 1, "fallback": fallback, "workspaces": {}}
    for workspace, filename in json.loads(args.sources.read_text()).items():
        root = Path(workspace).resolve()
        if filename:
            record = convert(Path(filename).resolve(), hashlib.sha256(str(root).encode()).hexdigest()[:16]+".png")
            record["kind"] = "application"
        else:
            record = {**fallback, "kind": "fallback"}
        catalog["workspaces"][str(root)] = record
    (args.output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
