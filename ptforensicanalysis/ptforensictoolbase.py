#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptforensictoolbase - Shared helpers for ptlibs-compliant forensic tools
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import hashlib
import json
import re
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ptlibs.ptprinthelper import ptprint

try:
    from ._constants import (IMAGE_FILE_KEYWORDS, EXIF_TIMEOUT, HASH_BLOCK_SIZE,
                              VALIDATE_TIMEOUT, MIN_IMAGE_BYTES, CORRUPT_SIZE_THRESHOLD)
except ImportError:
    from _constants import (IMAGE_FILE_KEYWORDS, EXIF_TIMEOUT, HASH_BLOCK_SIZE,
                             VALIDATE_TIMEOUT, MIN_IMAGE_BYTES, CORRUPT_SIZE_THRESHOLD)


def _forensic_sigint_handler(sig, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, _forensic_sigint_handler)


class ForensicToolBase:

    def _out(self) -> bool:
        return not getattr(self.args, "quiet", False)

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}
        ))

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=self._out())
        self._add_node(node_type, False, error=msg)
        return False

    @staticmethod
    def _sanitize_case_id(case_id: str) -> str:
        return re.sub(r'[^a-zA-Z0-9._-]', '_', case_id.strip())

    def _init_properties(self, version: str) -> None:
        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "analyst": self.analyst,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": version,
            "dryRun": self.dry_run,
        })

    def _print_header(self, title: str) -> None:
        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint(title, "TITLE", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

    @staticmethod
    def _file_sha256(path: Path) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(HASH_BLOCK_SIZE), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _progress(self, current: int, total: int, label: str = "") -> None:
        if not self._out() or total == 0:
            return
        pct = min(int(100 * current / total), 100)
        filled = pct // 5
        arrow = ">" if pct < 100 else ""
        empty = 20 - filled - len(arrow)
        bar = "=" * filled + arrow + " " * empty
        suffix = f"  {label}" if label else ""
        print(f"\r  [{bar}] {pct:3d}%{suffix}", end="", flush=True)
        if pct >= 100:
            print()

    def _progress_bytes(self, read: int, total: int, elapsed: float) -> None:
        if not self._out():
            return
        spd = (read / (1024 ** 2)) / elapsed if elapsed > 0 else 0.0
        read_gb = read / (1024 ** 3)
        total_gb = total / (1024 ** 3) if total else read_gb
        self._progress(read, total or read, f"{read_gb:.1f}/{total_gb:.1f} GB  {spd:.0f} MB/s")

    def _get_device_size(self, device: str) -> int:
        for cmd in [
            ["blockdev", "--getsize64", device],
            ["lsblk", "-b", "-d", "-n", "-o", "SIZE", device],
        ]:
            r = self._run_command(cmd, timeout=5)
            if r["success"] and r["stdout"].strip().isdigit():
                return int(r["stdout"].strip())
        return 0

    @staticmethod
    def confirm_write_blocker() -> bool:
        ptprint("\n" + "!" * 70, "WARNING", condition=True)
        ptprint("CRITICAL: WRITE-BLOCKER MUST BE CONNECTED",
                "WARNING", condition=True, colortext=True)
        ptprint("!" * 70, "WARNING", condition=True)
        for line in [
            "  1. Hardware write-blocker is physically connected",
            "  2. LED indicator shows PROTECTED",
            "  3. Source media connected THROUGH the write-blocker",
            "  4. Target storage has sufficient free space",
        ]:
            ptprint(line, "TEXT", condition=True)

        while True:
            resp = input("\nConfirm write-blocker is active [y/N]: ").strip().lower()
            if resp in ("y", "yes"):
                ok = True
                break
            if resp in ("n", "no", ""):
                ok = False
                break
            ptprint("Please enter 'y' or 'n'.", "WARNING", condition=True)

        sym = "✓" * 70 if ok else "✗" * 70
        lv = "OK" if ok else "ERROR"
        ptprint("\n" + sym, lv, condition=True)
        ptprint("CONFIRMED - proceeding" if ok else "NOT CONFIRMED - aborted",
                lv, condition=True, colortext=True)
        ptprint(sym, lv, condition=True)
        return ok

    def _validate_image_file(self, filepath: Path) -> Tuple[str, Dict]:
        info: Dict = {"size": 0, "imageFormat": None, "dimensions": None}

        try:
            info["size"] = filepath.stat().st_size
        except Exception as exc:
            return "invalid", {**info, "error": str(exc)}

        if info["size"] < MIN_IMAGE_BYTES:
            return "invalid", info

        r = self._run_command(["file", "-b", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if r["success"] and not any(kw in r["stdout"].lower()
                                     for kw in IMAGE_FILE_KEYWORDS):
            return "invalid", info

        if not self._check_command("identify"):
            return "corrupted" if info["size"] > CORRUPT_SIZE_THRESHOLD else "invalid", info

        r = self._run_command(["identify", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if r["success"]:
            m = re.search(r"(\w+)\s+(\d+)x(\d+)", r["stdout"])
            if m:
                info["imageFormat"] = m.group(1)
                info["dimensions"] = f"{m.group(2)}x{m.group(3)}"
            return "valid", info

        return ("corrupted" if info["size"] > CORRUPT_SIZE_THRESHOLD else "invalid"), info

    def _extract_fs_metadata(self, filepath: Path) -> Dict:
        meta: Dict = {}
        try:
            st = filepath.stat()
            meta = {
                "sizeBytes": st.st_size,
                "modifiedTime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "accessedTime": datetime.fromtimestamp(st.st_atime, tz=timezone.utc).isoformat(),
                "createdTime": datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
            }
        except Exception as exc:
            meta["error"] = str(exc)
        return meta

    def _extract_exif_metadata(self, filepath: Path) -> Tuple[Dict, bool]:
        exif_data: Dict = {}
        has_exif = False

        r = self._run_command(
            ["exiftool", "-json", "-charset", "utf8", str(filepath)],
            timeout=EXIF_TIMEOUT)
        if r["success"]:
            try:
                data = json.loads(r["stdout"])
                if data:
                    exif_data = data[0]
                    if ({"DateTimeOriginal", "CreateDate", "GPSLatitude",
                         "Make", "Model"} & set(data[0])):
                        has_exif = True
            except Exception as exc:
                exif_data = {"parseError": str(exc)}
        return exif_data, has_exif

    def _check_command(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False

    def _run_command(self, cmd: List[str], timeout: int = 300,
                     binary: bool = False) -> Dict[str, Any]:
        if self.dry_run:
            return {"success": True, "stdout": b"" if binary else "",
                    "stderr": "", "returncode": 0}
        try:
            if binary:
                proc = subprocess.run(cmd, capture_output=True,
                                      timeout=timeout, check=False)
                return {
                    "success": proc.returncode == 0,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr.decode(errors="replace").strip(),
                    "returncode": proc.returncode,
                }
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": b"" if binary else "",
                    "stderr": f"Timeout after {timeout}s", "returncode": -1}
        except Exception as exc:
            return {"success": False, "stdout": b"" if binary else "",
                    "stderr": str(exc), "returncode": -1}