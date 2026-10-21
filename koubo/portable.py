"""Relocate cached export references when a portable data folder moves."""
import json
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED


def rewrite_references(directory, replacements):
    pairs = []
    for old, new in replacements:
        old, new = str(old), str(new)
        pairs.extend([(old, new), (old.replace('\\', '/'), new.replace('\\', '/')),
                      (quote(old.replace('\\', '/'), safe='/:'), quote(new.replace('\\', '/'), safe='/:'))])
    pairs.sort(key=lambda p: len(p[0]), reverse=True)

    def replace(value):
        if isinstance(value, str):
            for old, new in pairs:
                value = value.replace(old, new)
            return value
        if isinstance(value, list):return [replace(v) for v in value]
        if isinstance(value, dict):return {k: replace(v) for k, v in value.items()}
        return value

    def rewrite(name, raw):
        suffix = Path(name).suffix.lower()
        if suffix not in ('.json', '.xml', '.txt'):return raw
        try:
            text = raw.decode('utf-8-sig')
            if suffix == '.json':
                value = json.loads(text)
                updated = replace(value)
                return json.dumps(updated, ensure_ascii=False, indent=2).encode('utf-8') if updated != value else raw
            updated = replace(text)
            return updated.encode('utf-8') if updated != text else raw
        except (UnicodeError, ValueError):return raw

    for path in directory.rglob('*'):
        if not path.is_file():continue
        if path.suffix.lower() == '.zip':
            with ZipFile(path) as archive:
                items = [(info, archive.read(info)) for info in archive.infolist()]
            updated = [(info, rewrite(info.filename, raw)) for info, raw in items]
            if any(a[1] != b[1] for a, b in zip(items, updated)):
                temporary = path.with_suffix('.zip.relocating')
                with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
                    for info, raw in updated:archive.writestr(info, raw)
                temporary.replace(path)
        elif path.suffix.lower() in ('.json', '.xml', '.txt'):
            raw = path.read_bytes(); updated = rewrite(path.name, raw)
            if updated != raw:path.write_bytes(updated)


def relocate(directory):
    marker = directory / 'portable.json'
    if not marker.is_file():return
    config = json.loads(marker.read_text(encoding='utf-8'))
    old = config.get('last_data_root')
    if old and Path(old) != directory:
        rewrite_references(directory, [(old, directory)])
    config['last_data_root'] = str(directory)
    marker.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
