#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptmediareadability - Forensic media readability diagnostic
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptmediareadability"

SMART_CHECKS = {
    "reallocated_sector":     ("Reallocated_Sector_Ct", 50),
    "current_pending_sector": ("Current_Pending_Sector",  0),
    "uncorrectable":          ("Offline_Uncorrectable",   0),
}
ENCRYPTION_MARKERS = {"crypto_luks": "LUKS", "bitlocker": "BitLocker", "veracrypt": "VeraCrypt"}
SPEED_THRESHOLDS = {"good": 20.0, "acceptable": 5.0}
EXIT_CODES = {"READABLE": 0, "PARTIAL": 1, "UNREADABLE": 2}


class PtMediaReadability(ForensicToolBase):
    """Forensic media readability diagnostic - NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.device = args.device

        self.detection_results: Dict = {}
        self.diagnostic_tests: List = []
        self.critical_findings: List = []
        self._stats = {"testsRun": 0, "testsPassed": 0, "testsFailed": 0}
        self.media_status: str = "UNKNOWN"
        self.recommended_tool: Optional[str] = None

        if not self.dry_run:
            if not self.device.startswith("/dev/"):
                ptprint(f"Invalid device path: {self.device}", "ERROR", condition=True)
                sys.exit(99)
            if not os.path.exists(self.device):
                ptprint(f"Device not found: {self.device}", "ERROR", condition=True)
                sys.exit(99)

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"devicePath": self.device})

    def _parse_smart_warnings(self, stdout: str) -> List[str]:
        warns = []
        for line in stdout.splitlines():
            parts = line.split()
            for keyword, (label, limit) in SMART_CHECKS.items():
                if keyword in line.lower():
                    raw = next((int(p) for p in reversed(parts) if p.isdigit()), None)
                    if raw is not None and raw > limit:
                        warns.append(f"{label} = {raw}")
                    break
        return warns

    def _detect_encryption(self, output: str) -> Optional[str]:
        return next((enc for marker, enc in ENCRYPTION_MARKERS.items()
                     if marker in output.lower()), None)

    def _is_raid_member(self, mdadm_output: str) -> bool:
        return any(kw in mdadm_output for kw in ("MD_LEVEL", "ARRAY"))

    def _categorize_speed(self, speed: float) -> tuple:
        if speed >= SPEED_THRESHOLDS["good"]:
            return "GOOD", "OK"
        if speed >= SPEED_THRESHOLDS["acceptable"]:
            return "ACCEPTABLE", "WARNING"
        return "CRITICALLY LOW", "ERROR"

    def _calculate_test_positions(self, size: int) -> List[tuple]:
        if size > 100 * 1_048_576:
            return [("start", 2048), ("middle", size // 2), ("end", size - 10 * 1_048_576)]
        return [("start", 2048), ("middle", 1_048_576), ("end", 10 * 1_048_576)]

    def _record_test(self, test_id: int, name: str, success: bool,
                     extra: Optional[Dict] = None) -> bool:
        entry = {"testId": test_id, "testName": name, "success": success}
        if extra:
            entry.update(extra)
        self.diagnostic_tests.append(entry)
        self._stats["testsPassed" if success else "testsFailed"] += 1
        self._stats["testsRun"] += 1
        return success

    def pre_detect(self) -> bool:
        self._print_header("PHASE 0: Pre-Detection")
        if not self._test_lsblk():
            return False
        self._test_blkid()
        self._test_smartctl()
        self._test_hdparm()
        self._test_mdadm()
        self._add_node("preDetection", True,
                       criticalFindings=len(self.critical_findings),
                       detectionResults=self.detection_results)
        return True

    def _test_lsblk(self) -> bool:
        ptprint("\n[0a] lsblk - device detection", "SUBTITLE", condition=self._out())
        if not self._check_command("lsblk"):
            self.detection_results["lsblk"] = {"error": "command not found"}
            return self._fail("preDetection", "lsblk not found")

        r = self._run_command(
            ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MODEL,SERIAL,TRAN", self.device])
        if not r["success"] and not self.dry_run:
            self.detection_results["lsblk"] = {"visible": False, "error": r["stderr"]}
            return self._fail("preDetection", f"Device not detected: {r['stderr']}")

        lsblk_out = r["stdout"] if r["stdout"] else "(dry-run)"
        size = self._get_device_size(self.device)
        ptprint(f"✓ Device detected:\n{lsblk_out}", "OK", condition=self._out())
        if size:
            ptprint(f"  Size: {size:,} bytes ({size / (1024**3):.2f} GB)",
                    "TEXT", condition=self._out())
        self.detection_results["lsblk"] = {"visible": True, "output": lsblk_out, "sizeBytes": size}
        return True

    def _test_blkid(self) -> None:
        ptprint("\n[0b] blkid - filesystem & encryption", "SUBTITLE", condition=self._out())
        if not self._check_command("blkid"):
            self.detection_results["blkid"] = {"error": "command not found"}
            return
        r = self._run_command(["blkid", self.device])
        out = r["stdout"] or r["stderr"] or "(no response)"
        enc = self._detect_encryption(out)
        if enc:
            self.critical_findings.append(f"Encryption detected: {enc} - recovery key required")
            ptprint(f"⚠ ENCRYPTION: {enc} detected!", "WARNING", condition=self._out(), colortext=True)
            ptprint("Recovery key/password REQUIRED for data access",
                    "WARNING", condition=self._out())
        else:
            ptprint(f"✓ {out}", "OK", condition=self._out())
        self.detection_results["blkid"] = {"output": out, "encrypted": bool(enc), "encryptionType": enc}

    def _test_smartctl(self) -> None:
        ptprint("\n[0c] smartctl - SMART health", "SUBTITLE", condition=self._out())
        if not self._check_command("smartctl"):
            self.detection_results["smartctl"] = {"error": "command not found"}
            return
        r = self._run_command(["smartctl", "-a", self.device])
        avail = r["success"] or "SMART support" in r["stdout"]
        warns = self._parse_smart_warnings(r["stdout"]) if avail and r["stdout"] else []
        if warns:
            for w in warns:
                self.critical_findings.append(f"SMART: {w}")
                ptprint(f"⚠ SMART WARNING: {w}", "WARNING", condition=self._out())
        else:
            ptprint("✓ SMART data OK" if avail else "✓ Not SMART-capable (normal for flash media)",
                    "OK", condition=self._out())
        self.detection_results["smartctl"] = {"smartAvailable": avail, "smartWarnings": warns}

    def _test_hdparm(self) -> None:
        ptprint("\n[0d] hdparm - TRIM detection", "SUBTITLE", condition=self._out())
        if not self._check_command("hdparm"):
            self.detection_results["hdparm"] = {"error": "command not found"}
            return
        r = self._run_command(["hdparm", "-I", self.device])
        trim = any("trim" in line and "supported" in line and line.strip().startswith("*")
                   for line in r["stdout"].lower().splitlines())
        if trim:
            self.critical_findings.append("TRIM active - deleted data may be physically erased")
            ptprint("⚠ TRIM ACTIVE!", "WARNING", condition=self._out(), colortext=True)
            ptprint("    Recovery may be INCOMPLETE - deleted data physically removed",
                    "WARNING", condition=self._out())
        else:
            ptprint("✓ TRIM not active or not supported", "OK", condition=self._out())
        self.detection_results["hdparm"] = {"trimActive": trim}

    def _test_mdadm(self) -> None:
        ptprint("\n[0e] mdadm - RAID configuration", "SUBTITLE", condition=self._out())
        if not self._check_command("mdadm"):
            self.detection_results["mdadm"] = {"error": "command not found"}
            return
        r = self._run_command(["mdadm", "--examine", self.device])
        is_raid = r["success"] and self._is_raid_member(r["stdout"] + r.get("stderr", ""))
        if is_raid:
            self.critical_findings.append("RAID member - full array required for recovery")
            ptprint("⚠ RAID MEMBER DETECTED!", "WARNING", condition=self._out(), colortext=True)
            ptprint("Full RAID array required for complete recovery",
                    "WARNING", condition=self._out())
        else:
            ptprint("✓ Not a RAID member", "OK", condition=self._out())
        self.detection_results["mdadm"] = {
            "isRaidMember": is_raid,
            "raidInfo":     r["stdout"] if is_raid else None,
        }

    def tests(self) -> bool:
        self._print_header("PHASE 1: Diagnostic Tests")
        if not self._test_first_sector():
            return False
        seq_ok = self._test_sequential_read()
        self._test_random_positions()
        if seq_ok or self.dry_run:
            self._test_read_speed()
        else:
            ptprint("\nTest 4/4: Speed - SKIPPED (sequential read failed)",
                    "WARNING", condition=self._out())
        self._add_node("diagnosticTests", True,
                       testsRun=self._stats["testsRun"],
                       testsPassed=self._stats["testsPassed"],
                       testsFailed=self._stats["testsFailed"],
                       tests=self.diagnostic_tests)
        return True

    def _test_first_sector(self) -> bool:
        ptprint("\nTest 1/4: First Sector (512 B)", "SUBTITLE", condition=self._out())
        r = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", "bs=512", "count=1", "status=none"])
        ptprint("✓ First sector readable" if r["success"] else
                "✗ CRITICAL: First sector FAILED - media UNREADABLE",
                "OK" if r["success"] else "ERROR", condition=self._out(),
                colortext=not r["success"])
        self._record_test(1, "First Sector", r["success"],
                          {"bytesRead": 512 if r["success"] else 0})
        return r["success"] or self.dry_run

    def _test_sequential_read(self) -> bool:
        ptprint("\nTest 2/4: Sequential Read (1 MB)", "SUBTITLE", condition=self._out())
        r = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", "bs=512", "count=2048", "status=none"],
            timeout=60)
        ptprint("✓ Sequential read OK" if r["success"] else "✗ Sequential read FAILED",
                "OK" if r["success"] else "ERROR", condition=self._out())
        self._record_test(2, "Sequential Read 1 MB", r["success"], {"bytesRead": 1_048_576 if r["success"] else 0})
        return r["success"]

    def _test_random_positions(self) -> bool:
        ptprint("\nTest 3/4: Random Read (3 positions)", "SUBTITLE", condition=self._out())
        size = self._get_device_size(self.device)
        results = []
        for label, offset in self._calculate_test_positions(size):
            r = self._run_command(
                ["dd", f"if={self.device}", "of=/dev/null",
                 "bs=512", "count=1", f"skip={offset // 512}", "status=none"])
            results.append({"position": label, "offsetBytes": offset, "success": r["success"]})
            ptprint(f"  {'✓' if r['success'] else '✗'} {label.capitalize()}",
                    "OK" if r["success"] else "ERROR", condition=self._out())
        all_ok = all(x["success"] for x in results)
        self._record_test(3, "Random Read", all_ok, {
            "positions":       results,
            "successfulReads": sum(1 for x in results if x["success"]),
            "totalReads":      len(results),
        })
        return all_ok

    def _test_read_speed(self) -> None:
        ptprint("\nTest 4/4: Read Speed (10 MB)", "SUBTITLE", condition=self._out())
        t0 = time.time()
        r = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null",
             "bs=512", "count=20480", "status=progress"], timeout=120)
        dur = time.time() - t0
        speed = (10 / dur) if r["success"] and dur > 0 else 0.0
        if r["success"]:
            tag, level = self._categorize_speed(speed)
            if speed < SPEED_THRESHOLDS["acceptable"]:
                self.critical_findings.append(f"Low read speed: {speed:.1f} MB/s")
                ptprint("    WARNING: Imaging will be very slow or may fail",
                        "WARNING", condition=self._out())
            ptprint(f"✓ Speed: {speed:.1f} MB/s ({tag})", level, condition=self._out())
        else:
            tag = "FAILED"
            ptprint("✗ Speed test FAILED", "ERROR", condition=self._out())
        self._record_test(4, "Read Speed", r["success"],
                          {"speedMBps": round(speed, 2), "speedStatus": tag})

    def classify(self) -> None:
        t = {test["testId"]: test["success"] for test in self.diagnostic_tests}
        if t:
            if all(t.values()):
                self.media_status, self.recommended_tool = "READABLE", "dc3dd"
            elif t.get(1) and t.get(2):
                self.media_status, self.recommended_tool = "PARTIAL", "ddrescue"
            else:
                self.media_status, self.recommended_tool = "UNREADABLE", "Physical repair required"
        self._add_node("readabilityClassification", True,
                       mediaStatus=self.media_status,
                       recommendedTool=self.recommended_tool)

    def _print_summary(self) -> None:
        self._print_header("SUMMARY")
        ptprint(f"Device: {self.device}", "TEXT", condition=self._out())
        ptprint(f"Case: {self.case_id}", "TEXT", condition=self._out())
        ptprint(f"Media status: {self.media_status}", "TEXT", condition=self._out())
        ptprint(f"Recommended tool: {self.recommended_tool}", "TEXT", condition=self._out())
        ptprint(f"Tests: {self._stats['testsPassed']}/{self._stats['testsRun']} passed",
                "TEXT", condition=self._out())
        if self.critical_findings:
            ptprint(f"\n⚠ CRITICAL FINDINGS ({len(self.critical_findings)}):",
                    "WARNING", colortext=True, condition=self._out())
            ptprint("   INFORM CLIENT BEFORE PROCEEDING:", "WARNING", condition=self._out())
            for finding in self.critical_findings:
                ptprint(f"   • {finding}", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"MEDIA READABILITY TEST v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.pre_detect() and not self.dry_run:
            self.media_status = "UNREADABLE"
            self.recommended_tool = "Physical repair required"
        else:
            self.tests()
        self.classify()
        if not self.dry_run:
            self._print_summary()

        self.ptjsonlib.add_properties({
            "compliance":       ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "mediaStatus":      self.media_status,
            "recommendedTool":  self.recommended_tool,
            "testsRun":         self._stats["testsRun"],
            "testsPassed":      self._stats["testsPassed"],
            "testsFailed":      self._stats["testsFailed"],
            "criticalFindings": self.critical_findings,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action":       f"Media readability test - result: {self.media_status}",
                "result":       "SUCCESS" if self.media_status in ("READABLE", "PARTIAL") else "UNREADABLE",
                "analyst":      self.analyst,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "selectedTool": self.recommended_tool,
            }
        ))
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        if not self.args.json_out:
            return None
        raw = self.ptjsonlib.get_result_json()
        Path(self.args.json_out).write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ JSON report saved: {self.args.json_out}", "OK", condition=True)
        return self.args.json_out


def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic media readability diagnostic - ptlibs compliant",
            "Classifies media as READABLE / PARTIAL / UNREADABLE via read-only tests",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
            "",
            "⚠ WRITE-BLOCKER IS ALWAYS REQUIRED - confirmed at every run",
        ]},
        {"usage": ["ptmediareadability <case-id> <device> [options]"]},
        {"usage_example": [
            "ptmediareadability PHOTORECOVERY-2025-01-26-001 /dev/sdb",
            "ptmediareadability CASE-001 /dev/sdb --analyst 'John Doe'",
            "ptmediareadability CASE-002 /dev/sdc --json-out result.json",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["device", "", "Device path (e.g., /dev/sdb) - REQUIRED"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without accessing the device"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Exit 0 = READABLE | Exit 1 = PARTIAL | Exit 2 = UNREADABLE | Exit 99 = error",
            "All operations are READ-ONLY",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("device")
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-j", "--json-out", default=None)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    args.json = bool(args.json_out)
    ptprinthelper.print_banner(SCRIPTNAME, __version__, False)
    return args


def main() -> int:
    try:
        args = parse_args()
        if not args.dry_run and not PtMediaReadability.confirm_write_blocker():
            ptprint("Test ABORTED - write-blocker is REQUIRED!", "ERROR", condition=True, colortext=True)
            return 99
        tool = PtMediaReadability(args)
        tool.run()
        tool.save_report()
        return EXIT_CODES.get(tool.media_status, 99)
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())