#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptimageverification - Forensic image hash verification tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import sys
import hashlib
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Skript je vždy spúšťaný ako nainštalovaný balíček cez Penterep platformu,
# relatívny import _version.py je preto vždy validný.
from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME          = "ptimageverification"
DEFAULT_OUTPUT_DIR  = "/var/forensics/images"
HASH_BLOCK_SIZE     = 4 * 1024 * 1024  # 4 MB chunks for memory-efficient hashing
PROGRESS_INTERVAL   = 1.0              # Report progress every 1 GB
TIMEOUT_HASH        = 7200             # 2 hours max for large images

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtImageVerification:
    """
    Forensic image hash verification tool – ptlibs compliant.

    Two-phase integrity verification:
      Phase 1 (Step 5): source_hash calculated during imaging (dc3dd / ddrescue)
      Phase 2 (Step 6): image_hash calculated from image file on disk

    Hash match mathematically proves bit-for-bit forensic integrity.
    Compliant with NIST SP 800-86 and ISO/IEC 27037:2012.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.image_path:        Optional[Path] = None
        self.image_format:      Optional[str]  = None
        self.image_size_bytes:  Optional[int]  = None
        self.source_hash:       Optional[str]  = None
        self.image_hash:        Optional[str]  = None

        self.ptjsonlib.add_properties({
            "caseId":                  self.case_id,
            "outputDirectory":         str(self.output_dir),
            "timestamp":               datetime.now(timezone.utc).isoformat(),
            "scriptVersion":           __version__,
            "imagePath":               None,
            "imageFormat":             None,
            "imageSizeBytes":          None,
            "sourceHash":              None,
            "imageHash":               None,
            "hashMatch":               None,
            "calculationTimeSeconds":  None,
            "verificationStatus":      "UNKNOWN",
            "dryRun":                  self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        """Append a result node to the JSON output."""
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type,
            properties={"success": success, **kwargs},
        ))

    def _check_command(self, cmd: str) -> bool:
        """Check if a shell command is available on PATH."""
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    # --- steps --------------------------------------------------------------

    def load_imaging_results(self) -> bool:
        """Step 1: Load source_hash from Step 5 JSON report."""
        ptprint("\n[1/4] Loading Imaging Results from Step 5", "TITLE", condition=not self.args.json)

        candidates = sorted(
            self.output_dir.glob(f"{self.case_id}_imaging*.json"),
            reverse=True
        )
        if not candidates:
            ptprint(f"Imaging results not found in {self.output_dir}.",
                    "ERROR", condition=not self.args.json)
            ptprint("Run Step 5 (ptforensicimaging) first.", "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="ImagingResults", error="Missing Step 5 results")
            return False

        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
            self.source_hash = (data.get("result", {})
                                    .get("properties", {})
                                    .get("sourceHash"))
        except Exception as exc:
            ptprint(f"Error reading imaging results: {exc}", "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="ImagingResults", error=str(exc))
            return False

        if not self.source_hash:
            ptprint("Source hash not found – Step 5 may not have completed successfully.",
                    "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="SourceHash", error="Source hash missing")
            return False

        # Validate: must be exactly 64 lowercase hex characters
        if len(self.source_hash) != 64 or not all(c in "0123456789abcdef"
                                                   for c in self.source_hash.lower()):
            ptprint(f"Invalid hash format: {self.source_hash}",
                    "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="SourceHashFormat", error="Invalid hash format")
            return False

        self.ptjsonlib.add_properties({"sourceHash": self.source_hash})
        ptprint(f"Source hash: {self.source_hash[:16]}...", "OK", condition=not self.args.json)
        self._add_node("prerequisiteCheck", True, checkName="ImagingResults",
                       sourceHash=self.source_hash, resultsFile=str(candidates[0]))
        return True

    def find_image_file(self) -> bool:
        """Step 2: Locate forensic image file (.dd, .raw, .E01)."""
        ptprint("\n[2/4] Locating Forensic Image File", "TITLE", condition=not self.args.json)

        for suffix in (".dd", ".raw", ".E01", ".e01"):
            path = self.output_dir / f"{self.case_id}{suffix}"
            if path.exists():
                self.image_path       = path
                self.image_format     = suffix.lower()
                self.image_size_bytes = path.stat().st_size
                size_gb = self.image_size_bytes / (1024 ** 3)

                self.ptjsonlib.add_properties({
                    "imagePath":       str(path),
                    "imageFormat":     self.image_format,
                    "imageSizeBytes":  self.image_size_bytes,
                })
                ptprint(f"Image: {path.name} | {size_gb:.2f} GB | {self.image_size_bytes:,} bytes",
                        "OK", condition=not self.args.json)
                self._add_node("imageFileCheck", True, imagePath=str(path),
                               imageFormat=self.image_format, imageSizeGB=round(size_gb, 2),
                               imageSizeBytes=self.image_size_bytes)
                return True

        ptprint(f"No image file found for case {self.case_id} in {self.output_dir}.",
                "ERROR", condition=not self.args.json)
        ptprint("Run Step 5 (ptforensicimaging) first.", "ERROR", condition=not self.args.json)
        self._add_node("imageFileCheck", False, error="Image file not found")
        return False

    def calculate_image_hash(self) -> bool:
        """Step 3: Calculate SHA-256 hash of image file."""
        ptprint("\n[3/4] Calculating Image File Hash", "TITLE", condition=not self.args.json)

        if self.image_format in (".dd", ".raw"):
            return self._hash_raw()
        elif self.image_format in (".e01",):
            return self._hash_e01()
        else:
            ptprint(f"Unsupported format: {self.image_format}", "ERROR", condition=not self.args.json)
            self._add_node("hashCalculation", False,
                           error="Unsupported format", imageFormat=self.image_format)
            return False

    def _hash_raw(self) -> bool:
        """Calculate SHA-256 for RAW images using Python hashlib (4 MB chunks)."""
        ptprint(f"Method: hashlib SHA-256 | File: {self.image_path.name}",
                "INFO", condition=not self.args.json)

        if self.dry_run:
            ptprint("[DRY-RUN] Simulating hash calculation.", "INFO", condition=not self.args.json)
            self.image_hash = self.source_hash  # Simulate MATCH in dry-run
            self.ptjsonlib.add_properties({"imageHash": self.image_hash})
            self._add_node("hashCalculation", True, dryRun=True, imageHash=self.image_hash)
            return True

        size_gb = self.image_size_bytes / (1024 ** 3)
        ptprint(f"Estimated time: ~{size_gb * 1024 / (200 * 60):.1f} min (assuming 200 MB/s)",
                "INFO", condition=not self.args.json)

        sha   = hashlib.sha256()
        read  = 0
        last  = 0.0
        t0    = time.time()

        try:
            with open(self.image_path, "rb") as f:
                while chunk := f.read(HASH_BLOCK_SIZE):
                    sha.update(chunk)
                    read += len(chunk)
                    current_gb = read / (1024 ** 3)
                    if current_gb - last >= PROGRESS_INTERVAL:
                        elapsed = time.time() - t0
                        speed   = (read / (1024 ** 2)) / elapsed if elapsed > 0 else 0
                        ptprint(f"Progress: {current_gb:.1f} GB | {speed:.0f} MB/s",
                                "INFO", condition=not self.args.json)
                        last = current_gb

            duration        = time.time() - t0
            self.image_hash = sha.hexdigest()
            avg_speed       = (self.image_size_bytes / (1024 ** 2)) / duration if duration > 0 else 0

            self.ptjsonlib.add_properties({
                "imageHash":               self.image_hash,
                "calculationTimeSeconds":  round(duration, 2),
            })
            ptprint(f"Completed in {duration:.0f}s ({duration/60:.1f} min) | "
                    f"{avg_speed:.0f} MB/s", "OK", condition=not self.args.json)
            ptprint(f"Image SHA-256: {self.image_hash}", "OK", condition=not self.args.json)
            self._add_node("hashCalculation", True, algorithm="SHA-256", method="hashlib",
                           imageHash=self.image_hash, durationSeconds=round(duration, 2),
                           averageSpeedMBps=round(avg_speed, 2))
            return True

        except Exception as exc:
            ptprint(f"Hash calculation failed: {exc}", "ERROR", condition=not self.args.json)
            self._add_node("hashCalculation", False, error=str(exc))
            return False

    def _hash_e01(self) -> bool:
        """Calculate hash for E01 images using ewfverify."""
        ptprint(f"Method: ewfverify | File: {self.image_path.name}",
                "INFO", condition=not self.args.json)

        if not self._check_command("ewfverify"):
            ptprint("ewfverify not found – install: sudo apt install libewf-tools",
                    "ERROR", condition=not self.args.json)
            self._add_node("hashCalculation", False, error="ewfverify not available")
            return False

        t0 = time.time()
        try:
            r = subprocess.run(
                ["ewfverify", "-d", "sha256", str(self.image_path)],
                capture_output=True, text=True, timeout=TIMEOUT_HASH
            )
            duration = time.time() - t0

            if r.returncode != 0:
                ptprint(f"ewfverify failed: {r.stderr}", "ERROR", condition=not self.args.json)
                self._add_node("hashCalculation", False,
                               error=r.stderr, returnCode=r.returncode)
                return False

            # Parse hash from ewfverify output
            for line in r.stdout.splitlines():
                if "sha256" in line.lower() and ":" in line:
                    self.image_hash = line.split(":")[-1].strip()
                    break

            if not self.image_hash:
                ptprint("Could not parse hash from ewfverify output.",
                        "ERROR", condition=not self.args.json)
                self._add_node("hashCalculation", False, error="Hash parsing failed")
                return False

            self.ptjsonlib.add_properties({
                "imageHash":               self.image_hash,
                "calculationTimeSeconds":  round(duration, 2),
            })
            ptprint(f"Completed in {duration:.0f}s", "OK", condition=not self.args.json)
            ptprint(f"Image SHA-256: {self.image_hash}", "OK", condition=not self.args.json)
            self._add_node("hashCalculation", True, algorithm="SHA-256", method="ewfverify",
                           imageHash=self.image_hash, durationSeconds=round(duration, 2))
            return True

        except subprocess.TimeoutExpired:
            ptprint(f"ewfverify timed out after {TIMEOUT_HASH}s.",
                    "ERROR", condition=not self.args.json)
            self._add_node("hashCalculation", False, error="Timeout")
            return False
        except Exception as exc:
            ptprint(f"Hash calculation failed: {exc}", "ERROR", condition=not self.args.json)
            self._add_node("hashCalculation", False, error=str(exc))
            return False

    def verify_hashes(self) -> bool:
        """Step 4: Compare source_hash (Step 5) with image_hash (just calculated)."""
        ptprint("\n[4/4] Verifying Hash Match", "TITLE", condition=not self.args.json)

        if not self.source_hash or not self.image_hash:
            ptprint("Missing hash values for comparison.", "ERROR", condition=not self.args.json)
            self._add_node("hashVerification", False, error="Missing hash values")
            return False

        ptprint(f"Source (Step 5): {self.source_hash}", "INFO", condition=not self.args.json)
        ptprint(f"Image  (file):   {self.image_hash}",  "INFO", condition=not self.args.json)

        match = self.source_hash == self.image_hash

        self.ptjsonlib.add_properties({
            "hashMatch":          match,
            "verificationStatus": "VERIFIED" if match else "MISMATCH",
        })

        if match:
            ptprint("HASH MATCH – image is bit-for-bit identical to source.",
                    "OK", condition=not self.args.json, colortext=True)
            self._add_node("hashVerification", True, hashMatch=True,
                           verificationStatus="VERIFIED",
                           sourceHash=self.source_hash, imageHash=self.image_hash)
        else:
            ptprint("HASH MISMATCH – CRITICAL ERROR. Repeat Step 5 (imaging).",
                    "ERROR", condition=not self.args.json, colortext=True)
            ptprint("Possible causes: I/O error during imaging, file corrupted on disk, "
                    "image modified after creation, or media degraded during imaging.",
                    "INFO", condition=not self.args.json)
            self._add_node("hashVerification", False, hashMatch=False,
                           verificationStatus="MISMATCH", criticalError=True,
                           sourceHash=self.source_hash, imageHash=self.image_hash)

        return match

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Execute the full verification workflow."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FORENSIC IMAGE VERIFICATION v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_imaging_results():
            self.ptjsonlib.set_status("finished"); return
        if not self.find_image_file():
            self.ptjsonlib.set_status("finished"); return
        if not self.calculate_image_hash():
            self.ptjsonlib.set_status("finished"); return

        match = self.verify_hashes()

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        if match:
            ptprint("VERIFICATION SUCCESSFUL", "OK", condition=not self.args.json)
            ptprint("Original media can be safely disconnected.", "OK", condition=not self.args.json)
            ptprint("Next: Step 7 – Media Specifications Documentation",
                    "INFO", condition=not self.args.json)
        else:
            ptprint("VERIFICATION FAILED – imaging must be repeated (Step 5).",
                    "ERROR", condition=not self.args.json)
            ptprint("Do NOT proceed with unverified image.", "ERROR", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """Output JSON report to stdout (--json) or to file."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        outfile = self.output_dir / f"{self.case_id}_verification.json"
        outfile.write_text(self.ptjsonlib.get_result_json(), encoding="utf-8")
        ptprint(f"Report saved: {outfile}", "OK", condition=not self.args.json)

        if self.image_hash and self.image_path:
            hash_file = self.output_dir / f"{self.case_id}_image.sha256"
            hash_file.write_text(f"{self.image_hash}  {self.image_path.name}\n")
            ptprint(f"Hash file saved: {hash_file}", "OK", condition=not self.args.json)

        return str(outfile)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List[Dict]:
    return [
        {"description": ["Forensic image hash verification tool – ptlibs compliant",
                         "Compares source_hash (Step 5 imaging) with image_hash (file on disk)"]},
        {"usage": ["ptimageverification <case-id> [options]"]},
        {"usage_example": ["ptimageverification PHOTO-2025-001",
                           "ptimageverification CASE-042 --json",
                           "ptimageverification TEST-001 --dry-run"]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate verification (simulates MATCH)"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"verification_process": [
            "1. Load source_hash from Step 5 JSON report",
            "2. Find forensic image file (.dd / .raw / .E01)",
            "3. Calculate SHA-256 hash of image file",
            "4. Compare – MATCH = verified, MISMATCH = repeat Step 5",
        ]},
        {"forensic_notes": [
            "Requires Step 5 (ptforensicimaging) results",
            "Hash match proves bit-for-bit integrity",
            "Supports RAW (.dd, .raw) and E01 formats",
            "Complies with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("-j", "--json",       action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address",   default=None)
    parser.add_argument("--socket-port",      default=None)
    parser.add_argument("--process-ident",    default=None)

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main() -> int:
    try:
        args = parse_args()

        verifier = PtImageVerification(args)
        verifier.run()
        verifier.save_report()

        status = verifier.ptjsonlib.json_data["result"]["properties"]["verificationStatus"]
        return {"VERIFIED": 0, "MISMATCH": 1}.get(status, 99)

    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())