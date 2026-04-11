"""Merge fresh GitHub traffic data with historical data stored in a gist.

Usage:
    python3 update_traffic.py --type clones
    python3 update_traffic.py --type views
"""

import argparse
import json
from collections import defaultdict


def merge_traffic(data_type: str) -> None:
    with open(f"{data_type}.json", "r") as f:
        current = json.load(f)

    with open(f"{data_type}_before.json", "r") as f:
        historical = json.load(f)

    entries = historical.get(data_type, [])
    timestamp_index = {entry["timestamp"]: i for i, entry in enumerate(entries)}

    for entry in current.get(data_type, []):
        ts = entry["timestamp"]
        if ts in timestamp_index:
            entries[timestamp_index[ts]] = entry
        else:
            entries.append(entry)

    entries.sort(key=lambda x: x["timestamp"])

    # Compress old entries into monthly buckets when list grows large
    if len(entries) > 100:
        daily_keep = 35
        to_compress = entries[: len(entries) - daily_keep]
        to_keep = entries[len(entries) - daily_keep :]

        monthly = defaultdict(lambda: {"count": 0, "uniques": 0})
        for entry in to_compress:
            month_key = entry["timestamp"][:7]
            monthly[month_key]["count"] += entry["count"]
            monthly[month_key]["uniques"] += entry["uniques"]

        compressed = [
            {"timestamp": month, "count": vals["count"], "uniques": vals["uniques"]}
            for month, vals in sorted(monthly.items())
        ]
        entries = compressed + to_keep

    total_count = sum(e["count"] for e in entries)
    total_uniques = sum(e["uniques"] for e in entries)

    result = {
        data_type: entries,
        "count": total_count,
        "uniques": total_uniques,
    }

    with open(f"{data_type}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge GitHub traffic data")
    parser.add_argument(
        "--type",
        required=True,
        choices=["clones", "views"],
        help="Type of traffic data to merge",
    )
    args = parser.parse_args()
    merge_traffic(args.type)
