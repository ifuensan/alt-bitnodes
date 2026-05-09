import json
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pycountry
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@lru_cache(maxsize=512)
def iso2_to_iso3(code: str) -> str | None:
    if not code:
        return None
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None

EXPORT_DIR = Path(
    os.environ.get(
        "BITNODES_EXPORT_DIR",
        "/mnt/datos/home_data/Work/myprojects/research/bitnodes/data/export/f9beb4d9",
    )
)

FIELDS = [
    "address", "port", "protocol_version", "user_agent", "timestamp",
    "services", "height", "hostname", "city", "country",
    "latitude", "longitude", "timezone", "asn", "asn_name",
]

app = FastAPI(title="Bitnodes Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")


def list_snapshots() -> list[int]:
    if not EXPORT_DIR.exists():
        return []
    return sorted(
        int(p.stem) for p in EXPORT_DIR.glob("*.json") if p.stem.isdigit()
    )


@lru_cache(maxsize=8)
def load_snapshot(timestamp: int) -> list[list]:
    path = EXPORT_DIR / f"{timestamp}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def to_dict(row: list) -> dict:
    return dict(zip(FIELDS, row))


@app.get("/")
def index() -> FileResponse:
    return FileResponse("templates/index.html")


@app.get("/api/snapshots")
def snapshots() -> dict:
    return {"timestamps": list_snapshots(), "export_dir": str(EXPORT_DIR)}


@app.get("/api/snapshot/{timestamp}")
def snapshot(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"timestamp": timestamp, "count": len(rows), "nodes": [to_dict(r) for r in rows]}


@app.get("/api/snapshot/{timestamp}/stats")
def snapshot_stats(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")

    countries = Counter(r[9] for r in rows if r[9])
    user_agents = Counter(r[3] for r in rows if r[3])
    asns = Counter(f"{r[13]} {r[14]}" for r in rows if r[13])
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    heights_sorted = sorted(heights)
    median_height = heights_sorted[len(heights_sorted) // 2] if heights_sorted else None

    countries_iso3 = []
    for cc, count in countries.items():
        iso3 = iso2_to_iso3(cc)
        if iso3:
            countries_iso3.append([iso3, count])

    return {
        "timestamp": timestamp,
        "total": len(rows),
        "countries_total": len(countries),
        "asns_total": len(asns),
        "user_agents_total": len(user_agents),
        "median_height": median_height,
        "top_countries": countries.most_common(15),
        "top_user_agents": user_agents.most_common(15),
        "top_asns": asns.most_common(15),
        "countries_iso3": countries_iso3,
        "height_histogram": dict(Counter(heights).most_common(10)),
    }


@app.get("/api/latest")
def latest() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    return snapshot(snaps[-1])


@app.get("/api/latest/stats")
def latest_stats() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    return snapshot_stats(snaps[-1])
