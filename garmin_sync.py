#!/usr/bin/env python3
"""
Garmin Connect daily sync (GitHub Actions).

- Restores the OAuth token store from the GARMIN_TOKENS_B64 secret
  (a base64-encoded zip of the garth token directory created once in
  Google Colab), logs in WITHOUT a password, fetches recent running
  activities plus daily context (sleep / HRV / training readiness /
  daily stats), and writes data/garmin_data.json.

- No GPS trackpoints are exported (privacy): only summary values and
  per-lap aggregates, which is what the training dashboard needs.

Environment:
  GARMIN_TOKENS_B64  (required) base64 zip of the token directory
  LOOKBACK_DAYS      (optional, default 14) how far back to fetch
  OUTPUT_PATH        (optional, default data/garmin_data.json)
"""

import base64
import io
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from garminconnect import Garmin

JST = timezone(timedelta(hours=9))
TOKEN_DIR = Path.home() / ".garmin_tokens"
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "data/garmin_data.json"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "14"))


def restore_tokens() -> None:
    b64 = os.environ.get("GARMIN_TOKENS_B64", "").strip()
    if not b64:
        sys.exit("GARMIN_TOKENS_B64 is not set. Run the Colab token setup first.")
    raw = base64.b64decode(b64)
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(TOKEN_DIR)
    files = [p.name for p in TOKEN_DIR.rglob("*") if p.is_file()]
    print(f"Token store restored: {files}")


def safe(label, fn, default=None):
    """Run fn(); on any error, log and return default (never crash the sync)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - one bad endpoint must not kill the run
        print(f"WARN: {label} failed: {type(e).__name__}: {e}")
        return default


# Keys kept from each activity summary (Garmin field names preserved so the
# dashboard side can map them 1:1). GPS / location fields are NOT included.
SUMMARY_KEYS = [
    "activityId", "activityName", "startTimeLocal", "startTimeGMT",
    "activityType", "distance", "duration", "elapsedDuration", "movingDuration",
    "averageSpeed", "maxSpeed", "averageHR", "maxHR",
    "averageRunningCadenceInStepsPerMinute", "maxRunningCadenceInStepsPerMinute",
    "averageStrideLength", "avgGroundContactTime", "avgGroundContactBalance",
    "avgVerticalOscillation", "avgVerticalRatio",
    "avgPower", "maxPower", "normPower",
    "aerobicTrainingEffect", "anaerobicTrainingEffect",
    "trainingEffectLabel", "activityTrainingLoad",
    "elevationGain", "elevationLoss", "minElevation", "maxElevation",
    "calories", "averageTemperature", "maxTemperature", "minTemperature",
    "steps", "lapCount",
]

# Keys kept from each lap (split) DTO.
LAP_KEYS = [
    "lapIndex", "startTimeGMT", "distance", "elapsedDuration", "movingDuration",
    "averageSpeed", "maxSpeed", "averageHR", "maxHR",
    "averageRunCadence", "maxRunCadence", "averageStrideLength",
    "groundContactTime", "groundContactBalance", "verticalOscillation",
    "verticalRatio", "averagePower", "maxPower",
    "totalAscent", "totalDescent", "calories",
]


def pick(d, keys):
    if not isinstance(d, dict):
        return d
    return {k: d.get(k) for k in keys if k in d}


def fetch_activity(client: Garmin, summary: dict) -> dict:
    aid = summary["activityId"]
    out = pick(summary, SUMMARY_KEYS)
    splits = safe(f"splits {aid}", lambda: client.get_activity_splits(aid), {}) or {}
    laps = splits.get("lapDTOs") if isinstance(splits, dict) else None
    out["laps"] = [pick(lap, LAP_KEYS) for lap in laps] if laps else []
    weather = safe(f"weather {aid}", lambda: client.get_activity_weather(aid))
    if weather:
        out["weather"] = weather
    return out


def fetch_daily(client: Garmin, day: date) -> dict:
    iso = day.isoformat()
    entry = {"date": iso}
    sleep = safe(f"sleep {iso}", lambda: client.get_sleep_data(iso), {}) or {}
    entry["sleep"] = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
    hrv = safe(f"hrv {iso}", lambda: client.get_hrv_data(iso), {}) or {}
    entry["hrv"] = hrv.get("hrvSummary") if isinstance(hrv, dict) else None
    readiness = safe(f"readiness {iso}", lambda: client.get_training_readiness(iso))
    if isinstance(readiness, list):
        entry["readiness"] = readiness[0] if readiness else None
    else:
        entry["readiness"] = readiness
    stats = safe(f"stats {iso}", lambda: client.get_stats(iso))
    if stats:
        entry["stats"] = stats
    return entry


def main() -> None:
    restore_tokens()

    client = Garmin()
    # Token-based login: no password, no browser, no human verification.
    client.login(str(TOKEN_DIR))
    print("Garmin login OK (token store).")

    today = datetime.now(JST).date()
    start = today - timedelta(days=LOOKBACK_DAYS)

    activities_raw = safe(
        "activities_by_date",
        lambda: client.get_activities_by_date(
            start.isoformat(), today.isoformat(), "running"
        ),
        [],
    ) or []
    activities = [fetch_activity(client, a) for a in activities_raw]
    activities.sort(key=lambda a: a.get("startTimeLocal") or "")
    print(f"Fetched {len(activities)} running activities "
          f"({start.isoformat()} .. {today.isoformat()}).")

    daily = {}
    for offset in range(LOOKBACK_DAYS + 1):
        day = start + timedelta(days=offset)
        daily[day.isoformat()] = fetch_daily(client, day)

    payload = {
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "lookback_days": LOOKBACK_DAYS,
        "activities": activities,
        "daily": daily,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes).")


if __name__ == "__main__":
    main()
