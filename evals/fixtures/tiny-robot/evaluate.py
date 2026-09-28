"""Report the tiny synthetic fixture's observed success counts."""

import csv
from collections import defaultdict
from pathlib import Path


def main() -> None:
    totals = defaultdict(lambda: [0, 0])
    with (Path(__file__).parent / "episodes.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            totals[row["policy"]][0] += int(row["success"])
            totals[row["policy"]][1] += 1
    for policy in ("baseline", "candidate"):
        successes, episodes = totals[policy]
        print(f"{policy}: {successes}/{episodes}")


if __name__ == "__main__":
    main()
