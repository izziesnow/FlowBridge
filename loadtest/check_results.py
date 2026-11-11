"""Check a Locust run against NFR05 and print the figures for the write-up.

    python loadtest/check_results.py loadtest/results/run_stats.csv [--p95-ms 1000]
"""
import argparse
import csv
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stats_csv")
    parser.add_argument("--p95-ms", type=float, default=1000)
    args = parser.parse_args()

    with open(args.stats_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    print(f"{'Request':32} {'Count':>6} {'Fail':>5} {'Median':>7} {'p95':>6} {'Max':>6}  (ms)")
    for row in rows:
        print(f"{row['Name'][:32]:32} {row['Request Count']:>6} {row['Failure Count']:>5} "
              f"{row['Median Response Time']:>7} {row['95%']:>6} {float(row['Max Response Time']):>6.0f}")
    total = next(r for r in rows if r["Name"] == "Aggregated")
    p95, failures, count = float(total["95%"]), int(total["Failure Count"]), int(total["Request Count"])
    ok = p95 < args.p95_ms and failures == 0 and count > 0
    print(f"\nNFR05: aggregated p95 = {p95:.0f} ms over {count} requests, {failures} failures "
          f"(target: p95 < {args.p95_ms:.0f} ms, no failures) -> {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
