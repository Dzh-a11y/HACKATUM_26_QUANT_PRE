"""下载固定版本的官方二进制和头文件，校验 SHA-256；只写本示例 vendor/。"""

import hashlib
from pathlib import Path
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent / "vendor"
DUCKDB_VERSION = "2.0.0"
JSON_VERSION = "3.12.0"
ARCHIVES = {
    ("Darwin", "arm64"): ("osx-arm64", "c35d60080b31ba5d11a3ce505a6831be784f003b4c575d32a4c2badb3b41cdf0"),
    ("Darwin", "x86_64"): ("osx-amd64", "98fef9fcad856555ca0403fe4d9d6680acfd26c67e8c6f004d61a248d6bc0eff"),
    ("Linux", "x86_64"): ("linux-amd64", "993ad89e7dfca66cd6da994c2cad090c2fc160ddf9f550498a098ab4bb13cfb1"),
    ("Linux", "aarch64"): ("linux-arm64", "c60eecf91143ca6bbac55c4f4d40dc22520488b0ac257c86e0fe9a2b451cf2b7"),
}


def fetch(url, path, digest):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f"SHA-256 mismatch: {url}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def main():
    target = (platform.system(), platform.machine())
    if target not in ARCHIVES:
        raise SystemExit(f"No pinned archive for {target}; supply -DDUCKDB_DIR manually.")
    name, digest = ARCHIVES[target]
    ROOT.mkdir(exist_ok=True)
    archive = ROOT / "duckdb.tar.gz"
    fetch(f"https://github.com/duckdb/duckdb/releases/download/v{DUCKDB_VERSION}/duckdb-shared-libs-{name}.tar.gz", archive, digest)
    with tarfile.open(archive) as source:
        # Only known headers/shared libraries; ignore all path-bearing members.
        destination = ROOT / "duckdb"
        destination.mkdir(exist_ok=True)
        for member in source.getmembers():
            if member.isfile() and Path(member.name).name == member.name and member.name.endswith((".h", ".so", ".dylib")):
                with source.extractfile(member) as content:
                    (destination / member.name).write_bytes(content.read())
    fetch(f"https://raw.githubusercontent.com/nlohmann/json/v{JSON_VERSION}/single_include/nlohmann/json.hpp", ROOT / "json.hpp",
          "aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63")
    print(f"Ready: DuckDB {DUCKDB_VERSION}, nlohmann/json {JSON_VERSION}, {name}")


if __name__ == "__main__":
    main()
