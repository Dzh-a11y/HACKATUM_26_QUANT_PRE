"""同一输入、同一 DuckDB 版本/约束/事务；串行交替顺序测 C++ 和现有 NumPy。"""

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter

from generate_fixture import generate, PYTHON_ROOT
from verify_pair import verify_pair

ROOT = Path(__file__).resolve().parent
SCENARIOS = {"stream": dict(seconds=610, symbols=2, teams=2),
             "batch1000": dict(seconds=1, symbols=1000, teams=2),
             "batch10000": dict(seconds=1, symbols=10000, teams=2)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--cases", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--binary", type=Path, default=ROOT / "build/ingest_cpp")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--memory-limit", default="8GB")
    args = parser.parse_args()
    if min(args.repeats, args.threads) < 1:
        parser.error("positive repeats and threads required")
    binary = args.binary.resolve()
    if not binary.is_file():
        parser.error("build ingest_cpp first")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="comparison-", dir=output))
    report = dict(measured_at=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
                  python=platform.python_version(), repeats=args.repeats, warmup_rounds=1,
                  threads=args.threads, memory_limit=args.memory_limit,
                  binary_sha256=digest(binary), scenarios={},
                  scope="Same JSON fixture loaded outside write timer; both derive account snapshots. write_ms includes field/column conversion, three constrained tables, BEGIN/COMMIT. total_active_ms includes fixture decode, database open/create, calculation, JSONL flush/fsync, Parquet ZSTD, manifests and database close; excludes process startup/imports and final report write. No sleeping. JSON compared structurally. Not a production throughput guarantee.")
    report["source_sha256"] = {
        str(path.relative_to(ROOT.parent)): digest(path)
        for base, suffixes in [(ROOT, {".cpp", ".hpp", ".py"}), (PYTHON_ROOT, {".py"})]
        for path in base.rglob("*") if path.is_file() and path.suffix in suffixes
        and not any(part in {"vendor", "build", "build-sanitize", "output", "__pycache__"} for part in path.relative_to(base).parts)
    }
    report["compiler"] = subprocess.run(["c++", "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    report["cmake_build_type"] = "Release"  # validate the default build, allow an explicit custom binary with disclosure
    cache = binary.parent / "CMakeCache.txt"
    if cache.exists():
        values = [line.split("=", 1)[1] for line in cache.read_text().splitlines() if line.startswith("CMAKE_BUILD_TYPE:STRING=")]
        if values:
            report["cmake_build_type"] = values[0]
    else:
        report["cmake_build_type"] = "unknown/custom binary"
    for name in args.cases:
        config = SCENARIOS[name]
        fixture = directory / f"{name}.json"
        fixture_hash = generate(fixture, **config)
        samples = {"numpy": [], "cpp": []}
        for repetition in range(args.repeats + 1):
            paths = {}
            # No parallel benchmark processes. Rotate order after each paired round.
            order = ("numpy", "cpp") if repetition % 2 == 0 else ("cpp", "numpy")
            for implementation in order:
                destination = directory / f"{name}-{repetition}-{implementation}"
                paths[implementation] = destination
                command = ([sys.executable, str(ROOT / "python_worker.py")] if implementation == "numpy" else [str(binary), "--fast"])
                command += ["--input", str(fixture), "--output", str(destination), "--threads", str(args.threads), "--memory-limit", args.memory_limit]
                start = perf_counter()
                completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
                wall_ms = (perf_counter() - start) * 1000
                (directory / f"{destination.name}.log").write_text(completed.stdout + completed.stderr)
                if completed.returncode:
                    raise RuntimeError(f"{implementation} failed: {completed.stderr}")
                info = json.loads((destination / "run.json").read_text())
                if info["status"] != "completed":
                    raise RuntimeError("incomplete run")
                if repetition:
                    samples[implementation].append(dict(metrics=info["metrics"], process_wall_ms=wall_ms,
                                                        rows=info["rows"], run=destination.name))
            infos = [json.loads((paths[key] / "run.json").read_text()) for key in ("numpy", "cpp")]
            if infos[0]["source_id"] != infos[1]["source_id"] or infos[0]["duckdb_version"].lstrip("v") != infos[1]["duckdb_version"].lstrip("v"):
                raise AssertionError("different DuckDB engine versions")
            if infos[0]["runtime"] != infos[1]["runtime"]:
                raise AssertionError("different runtime settings")
            if digest(fixture) != fixture_hash:
                raise AssertionError("fixture changed")
            with (directory / f"{name}-{repetition}-verification.log").open("w") as log, contextlib.redirect_stdout(log):
                verify_pair(fixture, paths["numpy"], paths["cpp"])
            report["duckdb_version"], report["source_id"] = infos[0]["duckdb_version"], infos[0]["source_id"]
            report["numpy_version"] = infos[0]["numpy_version"]
            print(f"{name}: paired round {repetition}/{args.repeats}, exact values and constraints PASS", flush=True)
        medians = {implementation: {metric: median(sample["metrics"][metric] for sample in runs)
                                    for metric in ("input_decode_ms", "calculate_ms", "write_ms", "news_ms", "export_ms", "close_ms", "total_active_ms")}
                   for implementation, runs in samples.items()}
        report["scenarios"][name] = dict(config=config, fixture_sha256=fixture_hash,
                                         fixture_bytes=fixture.stat().st_size, medians_ms=medians, samples=samples,
                                         speedup={metric: medians["numpy"][metric] / medians["cpp"][metric]
                                                  for metric in ("write_ms", "total_active_ms")}, all_pairs_verified=True)
        (directory / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"{name}: {report['scenarios'][name]['speedup']}", flush=True)
    print(f"COMPARISON_DIR={directory}", flush=True)


if __name__ == "__main__":
    main()
