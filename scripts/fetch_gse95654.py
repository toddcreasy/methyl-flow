"""Fetch and downsample the GSE95654 runs listed in config/gse95654/runs.tsv.

For each sample:
1. prefetch the full-quality .sra file from NCBI (MD5-validated by prefetch).
   SRA Lite files, which replace quality scores with a constant, are rejected.
2. fasterq-dump it to FASTQ in a temporary directory.
3. seqtk sample a fixed number of reads with a fixed seed, gzip, and delete
   the full FASTQ. The same seed on R1 and R2 keeps read pairs in sync.

Tools run from the same pinned BioContainers images nf-core uses. Samples whose
output already exists are skipped, so the script is safe to re-run.

Usage: uv run python scripts/fetch_gse95654.py [--reads 5000000] [--seed 42]
"""

import argparse
import csv
import logging
import os
import shutil
import subprocess
from pathlib import Path

MANIFEST = Path("config/gse95654/runs.tsv")
DATA = Path("data")
SRA_DIR = DATA / "sra" / "gse95654"
TMP_DIR = DATA / "tmp" / "gse95654"
OUT_DIR = DATA / "fastq" / "gse95654"

SRA_TOOLS = "quay.io/biocontainers/sra-tools:3.2.1--h4304569_1"
SEQTK = "quay.io/biocontainers/seqtk:1.4--he4a0461_1"

log = logging.getLogger("fetch_gse95654")


def docker(image: str, *cmd: str) -> None:
    root = Path.cwd()
    subprocess.run(
        [
            "docker", "run", "--rm", "--platform", "linux/amd64",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-e", f"HOME=/w/{DATA}",
            "-v", f"{root}:/w", "-w", "/w",
            image, *cmd,
        ],
        check=True,
    )  # fmt: skip


def prefetch(run: str) -> Path:
    sra = SRA_DIR / run / f"{run}.sra"
    if sra.exists():
        return sra
    docker(SRA_TOOLS, "prefetch", "--max-size", "u", "-O", str(SRA_DIR), run)
    if not sra.exists():
        got = [p.name for p in (SRA_DIR / run).iterdir()]
        raise RuntimeError(f"{run}: no full-quality .sra file, got {got}")
    return sra


def fetch(row: dict, reads: int, seed: int) -> None:
    sample, run = row["sample"], row["run"]
    mates = ["1", "2"] if row["layout"] == "paired" else ["1"]
    outs = [OUT_DIR / f"{sample}_R{m}.fastq.gz" for m in mates]
    if all(o.exists() for o in outs):
        log.info("%s: done (cached)", sample)
        return

    sra = prefetch(run)
    log.info("%s: %s downloaded and validated", sample, run)

    tmp = TMP_DIR / run
    tmp.mkdir(parents=True, exist_ok=True)
    docker(SRA_TOOLS, "fasterq-dump", "--split-3", "--threads", "6",
           "--temp", str(tmp), "-O", str(tmp), str(sra))  # fmt: skip

    if len(mates) == 2:
        fastqs = [tmp / f"{run}_{m}.fastq" for m in mates]
    else:
        fastqs = [tmp / f"{run}.fastq"]
    for fq, out in zip(fastqs, outs, strict=True):
        part = out.with_suffix(".gz.part")
        sample_cmd = f"set -o pipefail && seqtk sample -2 -s {seed} {fq} {reads} | gzip -1 > {part}"
        docker(SEQTK, "sh", "-c", sample_cmd)
        part.rename(out)
    shutil.rmtree(tmp)
    log.info("%s: %d reads sampled with seed %d", sample, reads, seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reads", type=int, default=5_000_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    for d in (SRA_DIR, TMP_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    docker(SRA_TOOLS, "vdb-config", "--simplified-quality-scores", "no")

    with MANIFEST.open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            fetch(row, args.reads, args.seed)


if __name__ == "__main__":
    main()
