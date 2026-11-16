#!/usr/bin/env python3
"""Move finished run output to the external drive, in two steps (memory: run-output-external-drive):

1. copy every file of an item (a folder or a file under the repo) to ARCH/<repo-relative path>, hashing the
   source as it is read, then read the copy back with the page cache off (F_NOCACHE) and compare sha256;
   every file goes into the manifest (path, size, sha256);
2. only if every source file still has its recorded hash, remove the item and leave a symlink to the copy.

Run from a Terminal panel tab (processes started from Bash get EPERM on the drive).
usage: python3 move_runs.py MANIFEST LIST   (LIST: one repo-relative path per line, # comments)
"""
import fcntl
import hashlib
import os
import shutil
import sys
import time

REPO = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg"
ARCH = os.environ.get("EEG_ARCHIVE", "/Volumes/mukiebi/first_tapeout_archive")   # 11/16: set EEG_ARCHIVE for the SSD that replaces mukiebi
F_NOCACHE = getattr(fcntl, "F_NOCACHE", 48)
BUF = 8 << 20


def sha_file(path, nocache=False):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        if nocache:
            fcntl.fcntl(fd, F_NOCACHE, 1)
        while True:
            b = os.read(fd, BUF)
            if not b:
                break
            h.update(b)
    finally:
        os.close(fd)
    return h.hexdigest()


def copy_hash(src, dst):
    """copy src to dst (data only: no extended attributes, so no ._ files on exFAT), sha256 of what was read"""
    h = hashlib.sha256()
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            b = fi.read(BUF)
            if not b:
                break
            h.update(b)
            fo.write(b)
        fo.flush()
        os.fsync(fo.fileno())
    st = os.stat(src)
    os.utime(dst, (st.st_atime, st.st_mtime))
    return h.hexdigest()


def files_of(src):
    if os.path.isfile(src):
        return [src]
    out = []
    for dp, dn, fn in os.walk(src):
        dn.sort()
        for f in sorted(fn):
            out.append(os.path.join(dp, f))
    return out


def move(rel, manifest):
    src = os.path.join(REPO, rel)
    dst = os.path.join(ARCH, rel)
    if os.path.islink(src):
        print(f"skip {rel}: already a symlink -> {os.readlink(src)}", flush=True)
        return 0
    if not os.path.exists(src):
        print(f"skip {rel}: missing", flush=True)
        return 0
    if os.path.exists(dst):
        print(f"STOP {rel}: {dst} exists", flush=True)
        return 0
    t0 = time.time()
    fl = files_of(src)
    links = [f for f in fl if os.path.islink(f)]
    if links:
        print(f"STOP {rel}: symlinks inside ({links[:3]})", flush=True)
        return 0
    rows = []
    for f in fl:
        d = os.path.join(dst, os.path.relpath(f, src)) if os.path.isdir(src) else dst
        os.makedirs(os.path.dirname(d), exist_ok=True)
        h1 = copy_hash(f, d)
        h2 = sha_file(d, nocache=True)
        if h1 != h2:
            print(f"STOP {rel}: the copy of {f} reads back differently", flush=True)
            return 0
        rows.append((os.path.relpath(f, REPO), os.path.getsize(f), h1))
    if os.path.isdir(src):
        for dp, dn, fn in os.walk(src):                  # empty folders too
            os.makedirs(os.path.join(dst, os.path.relpath(dp, src)), exist_ok=True)
    with open(manifest, "a") as m:
        for p, n, h in rows:
            m.write(f"{p}\t{n}\t{h}\n")
    changed = [p for p, n, h in rows if sha_file(os.path.join(REPO, p)) != h]
    if changed or len(files_of(src)) != len(rows):
        print(f"KEEP {rel}: changed while copying ({changed[:3]}); copy left at {dst}", flush=True)
        return 0
    size = sum(n for _, n, _ in rows)
    if os.path.isdir(src):
        shutil.rmtree(src)
    else:
        os.remove(src)
    os.symlink(dst, src)
    print(f"moved {rel}: {len(rows)} files, {size / 1e9:.2f} GB, {time.time() - t0:.0f} s", flush=True)
    return size


def main():
    manifest, lst = sys.argv[1], sys.argv[2]
    items = [ln.strip() for ln in open(lst) if ln.strip() and not ln.startswith("#")]
    total = 0
    for rel in items:
        total += move(rel, manifest)
    st = os.statvfs(REPO)
    print(f"done: {total / 1e9:.2f} GB moved; internal disk free {st.f_bavail * st.f_frsize / 2**30:.1f} GiB", flush=True)


if __name__ == "__main__":
    main()
