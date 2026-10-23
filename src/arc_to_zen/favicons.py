from __future__ import annotations

import base64
from pathlib import Path

from .io import readonly_db
from .models import ArcData
from .paths import source_profile


def collect(source: Path, data: ArcData) -> tuple[dict, int]:
    images, unavailable = {}, 0
    for key in dict.fromkeys(s.profile for s in data.spaces):
        path = source_profile(source, key) / "Favicons"
        wanted = {t.url for s in data.spaces if s.profile == key for t in s.tabs}
        if not path.exists():
            unavailable += len(wanted)
            continue
        with readonly_db(path) as db:
            for url in wanted:
                row = db.execute(
                    "SELECT CAST(b.image_data AS BLOB) FROM icon_mapping m JOIN favicon_bitmaps b ON b.icon_id=m.icon_id WHERE m.page_url=? ORDER BY b.width DESC LIMIT 1",
                    (url,),
                ).fetchone()
                if not row or not row[0]:
                    unavailable += 1
                    continue
                raw = row[0]
                if len(raw) > 1024 * 1024:
                    unavailable += 1
                    continue
                mime = (
                    "image/png"
                    if raw.startswith(b"\x89PNG")
                    else "image/x-icon"
                    if raw.startswith(b"\0\0\1\0")
                    else None
                )
                if mime:
                    images[key, url] = "data:" + mime + ";base64," + base64.b64encode(raw).decode()
                else:
                    unavailable += 1
    return images, unavailable
