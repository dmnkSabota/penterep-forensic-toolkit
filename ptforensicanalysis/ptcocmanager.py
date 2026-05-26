#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptcocmanager - Chain of Custody manager (gate + consolidate)
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_OUTPUT_DIR
except ImportError:
    from _constants import DEFAULT_OUTPUT_DIR

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptcocmanager"

SCENARIO_CHAIN = "chain-of-custody"
SCENARIO_PHOTO = "photo-recovery"
SCENARIO_MALWARE = "malware"
SCENARIOS = (SCENARIO_CHAIN, SCENARIO_PHOTO, SCENARIO_MALWARE)

MODE_GATE = "gate"
MODE_CONSOLIDATE = "consolidate"
MODES = (MODE_GATE, MODE_CONSOLIDATE)

CASE_PREFIX_MAP = {
    "COC": SCENARIO_CHAIN,
    "PHOTORECOVERY": SCENARIO_PHOTO,
    "MALWARE": SCENARIO_MALWARE,
}

DISCOVERY_PATTERNS: Dict[str, List[str]] = {
    "imaging":         ["{cid}_imaging.json", "{cid}_imaging_result.json", "imaging_result.json"],
    "verification":    ["{cid}_verification.json", "{cid}_verification_report.json", "verification_report.json"],
    "readability":     ["{cid}_readability.json", "readability_result.json"],
    "volatile":        ["{cid}_volatile.json", "{cid}_volatile_result.json", "volatile_result.json"],
    "filesystem":      ["{cid}_filesystem_analysis.json"],
    "fs_recovery":     ["{cid}_recovery_report.json", "{cid}_filesystem_recovery.json"],
    "carving":         ["{cid}_carving.json", "{cid}_file_carving.json"],
    "consolidation":   ["{cid}_consolidation_report.json", "{cid}_photo_consolidation.json"],
    "integrity":       ["{cid}_integrity_validation.json"],
    "repair_decision": ["{cid}_repair_decisions.json"],
    "repair":          ["{cid}_repair_report.json"],
    "exif":            ["{cid}_exif_database.json", "{cid}_exif_analysis.json"],
    "static":          ["{cid}_static_analysis.json", "{cid}_static_result.json"],
    "artefacts":       ["{cid}_artefacts.json"],
    "ioc":             ["{cid}_ioc.json"],
    "threat":          ["{cid}_threat_intel.json"],
}

GATE_KINDS = ("imaging", "verification", "readability")

ARTEFACT_EXTRACTORS: Dict[str, List[Tuple[str, str, Optional[str]]]] = {
    "imaging":       [("forensic_image", "imagePath", "sourceHash")],
    "volatile":      [
        ("ram_dump", "ramDump", "ramDumpSha256"),
        ("process_list", "processListPath", "processListPathSha256"),
        ("network_connections", "networkConnectionsPath", "networkConnectionsPathSha256"),
    ],
    "consolidation": [("recovered_dataset", "consolidatedDir", None)],
    "carving":       [("carved_dataset", "outputDir", None)],
    "fs_recovery":   [("fs_recovered_dataset", "outputDir", None)],
    "repair":        [("repaired_dataset", "repairedDir", None)],
    "static":        [("static_analysis", "stringsFile", None)],
    "artefacts":     [("artefact_inventory", "output", None)],
    "ioc":           [("ioc_report", "output", None)],
    "threat":        [("threat_intel_report", "output", None)],
}


class PtCocManager(ForensicToolBase):
    """Chain of Custody manager - gate validation + final consolidation, NIST SP 800-86, ISO/IEC 27037:2012, NIST SP 800-61 Rev. 3."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.mode = args.mode
        self.scenario = self._resolve_scenario(args.scenario)

        self.storage_location = args.storage_location
        self.client_data = args.client_data
        self.incident_type = args.incident_type
        self.affected_system = args.affected_system
        self.detection_time = args.detection_time
        self.isolation_time = args.isolation_time

        self._reports: Dict[str, Dict] = {}
        self._report_paths: Dict[str, Path] = {}
        self._cross_valid = False
        self._ver_status = "UNKNOWN"

        self._explicit: Dict[str, Optional[Path]] = {
            "imaging":      Path(args.imaging_json) if args.imaging_json else None,
            "verification": Path(args.verification_json) if args.verification_json else None,
            "readability":  Path(args.readability_json) if args.readability_json else None,
            "volatile":     Path(args.volatile_json) if args.volatile_json else None,
        }

        self._init_properties(__version__)

    def _resolve_scenario(self, requested: Optional[str]) -> str:
        if requested:
            return requested
        prefix = self.case_id.split("-", 1)[0].upper() if "-" in self.case_id else self.case_id.upper()
        return CASE_PREFIX_MAP.get(prefix, SCENARIO_CHAIN)

    def _discover(self, kind: str) -> Optional[Path]:
        if kind in self._explicit and self._explicit[kind] is not None:
            return self._explicit[kind]
        for template in DISCOVERY_PATTERNS.get(kind, []):
            candidate = self.output_dir / template.format(cid=self.case_id)
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _props(data: Dict) -> Dict:
        return data.get("results", {}).get("properties", {})

    @staticmethod
    def _nodes(data: Dict) -> List[Dict]:
        return data.get("results", {}).get("nodes", [])

    def _load_json(self, path: Path, label: str) -> Optional[Dict]:
        if self.dry_run:
            return {}
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            ptprint(f"  ✗ Failed to parse {label}: {exc}", "ERROR", condition=self._out())
            return None

    def _kinds_to_load(self) -> List[str]:
        if self.mode == MODE_GATE:
            return list(GATE_KINDS)
        return list(DISCOVERY_PATTERNS.keys())

    def discover_reports(self) -> bool:
        self._print_header(f"PHASE 1: Discover reports  |  Mode: {self.mode}  |  Scenario: {self.scenario}")

        required = {"imaging", "verification"}
        found_any = False

        for kind in self._kinds_to_load():
            path = self._discover(kind)
            if path is None:
                if kind in required:
                    return self._fail("reportsDiscovered",
                                      f"Required report '{kind}' not found in {self.output_dir}. "
                                      f"Provide explicit path via flag.")
                if self.mode == MODE_CONSOLIDATE:
                    ptprint(f"  ○ {kind}: not present (skipped)", "INFO", condition=self._out())
                continue
            data = self._load_json(path, f"{kind} report")
            if data is None:
                if kind in required:
                    return self._fail("reportsDiscovered", f"Required report '{kind}' unreadable")
                continue
            self._reports[kind] = data
            self._report_paths[kind] = path
            found_any = True
            ptprint(f"  ✓ {kind}: {path.name}", "OK", condition=self._out())

        if not found_any and not self.dry_run:
            return self._fail("reportsDiscovered", "No reports discovered")

        self._add_node("reportsDiscovered", True,
                       loadedKinds=list(self._reports.keys()),
                       reportPaths={k: str(p) for k, p in self._report_paths.items()})
        return True

    def validate_chain(self) -> None:
        self._print_header("PHASE 2: Cross-Report Validation")

        if self.dry_run:
            self._cross_valid = True
            ptprint("  ○ Cross-validation skipped (dry-run)", "WARNING", condition=self._out())
            self._add_node("crossValidation", True, note="dry-run")
            return

        img_props = self._props(self._reports.get("imaging", {}))
        ver_props = self._props(self._reports.get("verification", {}))
        source_hash_img = img_props.get("sourceHash", "")
        source_hash_ver = ver_props.get("sourceHash", "")
        image_hash = ver_props.get("imageHash", "")
        ver_status = ver_props.get("verificationStatus", "UNKNOWN")
        self._ver_status = ver_status
        hash_match = ver_props.get("hashMatch", False)

        if not source_hash_img:
            self._cross_valid = False
            self._fail("crossValidation", "sourceHash missing from imaging report")
            return

        cross_ok = True
        if source_hash_ver and source_hash_img != source_hash_ver:
            ptprint("  ✗ sourceHash mismatch across reports", "ERROR", condition=self._out())
            cross_ok = False
        else:
            ptprint(f"  ✓ sourceHash: {source_hash_img[:16]}...", "OK", condition=self._out())

        if ver_status != "VERIFIED":
            ptprint(f"  ✗ Image not verified: {ver_status}", "ERROR", condition=self._out())
            cross_ok = False
        else:
            ptprint("  ✓ Verification status: VERIFIED", "OK", condition=self._out())

        self._cross_valid = cross_ok
        self._add_node("crossValidation", cross_ok,
                       sourceHash=source_hash_img,
                       imageHash=image_hash,
                       hashMatch=hash_match,
                       verificationStatus=ver_status,
                       crossValid=cross_ok)

    def build_timeline(self) -> List[Dict]:
        self._print_header("PHASE 3: Build CoC Timeline")
        entries: List[Dict] = []

        for kind, report in self._reports.items():
            for node in self._nodes(report):
                if node.get("type") != "chainOfCustodyEntry":
                    continue
                props = node.get("properties", {})
                entries.append({
                    "timestamp": props.get("timestamp", ""),
                    "action": props.get("action", ""),
                    "analyst": props.get("analyst", ""),
                    "result": props.get("result", ""),
                    "tool": props.get("tool", ""),
                    "sourceReport": kind,
                })

        entries.sort(key=lambda e: e["timestamp"] or "")
        ptprint(f"  ✓ Timeline assembled: {len(entries)} CoC entries from {len(self._reports)} reports",
                "OK", condition=self._out())

        self._add_node("cocTimeline", True,
                       entryCount=len(entries),
                       sourceReports=list(self._reports.keys()),
                       entries=entries)
        return entries

    def _collect_artefacts(self) -> List[Dict]:
        artefacts: List[Dict] = []
        for kind, report in self._reports.items():
            props = self._props(report)
            for atype, path_key, hash_key in ARTEFACT_EXTRACTORS.get(kind, []):
                path_value = props.get(path_key)
                if not path_value:
                    continue
                entry: Dict = {"type": atype, "path": path_value, "sourceReport": kind}
                if hash_key:
                    sha = props.get(hash_key)
                    if sha:
                        entry["sha256"] = sha
                if kind == "imaging":
                    size = props.get("imageSizeBytes")
                    if size:
                        entry["sizeBytes"] = size
                artefacts.append(entry)
        return artefacts

    def _scenario_specific_block(self) -> Dict:
        if self.scenario == SCENARIO_MALWARE:
            block = {
                "incident": {
                    "type": self.incident_type or "",
                    "affectedSystem": self.affected_system or "",
                    "detectionTime": self.detection_time or "",
                    "isolationTime": self.isolation_time or "",
                },
                "legalDeadlines": {
                    "reference": "Zákon č. 264/2025 Sb.",
                    "article":   "§29",
                },
            }
            if self.detection_time:
                try:
                    dt = datetime.fromisoformat(self.detection_time.replace("Z", "+00:00"))
                    block["legalDeadlines"].update({
                        "nukib24h": dt.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                        "gdpr72h": "computed_from_detectionTime",
                    })
                except ValueError:
                    pass
            return block
        if self.scenario == SCENARIO_PHOTO:
            return {"client": {"data": self.client_data or ""}}
        return {"storage": {"location": self.storage_location or ""}}

    def generate_coc_documentation(self) -> None:
        self._print_header("PHASE 4: CoC Documentation")

        img_props = self._props(self._reports.get("imaging", {}))
        ver_props = self._props(self._reports.get("verification", {}))
        read_props = self._props(self._reports.get("readability", {}))
        critical_findings = read_props.get("criticalFindings", [])

        coc_props = {
            "scenario": self.scenario,
            "mode": self.mode,
            "storageLocation": self.storage_location or "",
            "documentationTimestamp": datetime.now(timezone.utc).isoformat(),
            "sourceHash": img_props.get("sourceHash", ""),
            "imageHash": ver_props.get("imageHash", ""),
            "imagePath": img_props.get("imagePath", ""),
            "imageSizeBytes": img_props.get("imageSizeBytes"),
            "toolVersion": img_props.get("toolVersion", ""),
            "writeBlockerConfirmed": img_props.get("writeBlockerConfirmed", False),
            "mediaStatus": read_props.get("mediaStatus", "UNKNOWN"),
            "crossValidated": self._cross_valid,
            "scenarioSpecific": self._scenario_specific_block(),
            "artefacts": self._collect_artefacts(),
        }
        if critical_findings:
            coc_props["criticalFindings"] = critical_findings

        self._add_node("cocDocumentation", True, **coc_props)
        ptprint("  ✓ CoC documentation node generated", "OK", condition=self._out())
        if self.storage_location:
            ptprint(f"  Storage: {self.storage_location}", "INFO", condition=self._out())
        if self.scenario == SCENARIO_MALWARE and self.incident_type:
            ptprint(f"  Incident: {self.incident_type}", "INFO", condition=self._out())
            if self.affected_system:
                ptprint(f"  Affected: {self.affected_system}", "INFO", condition=self._out())
        if self.scenario == SCENARIO_PHOTO and self.client_data:
            ptprint(f"  Client: {self.client_data}", "INFO", condition=self._out())
        if critical_findings:
            ptprint(f"  ⚠ {len(critical_findings)} critical findings",
                    "WARNING", condition=self._out())

    def generate_manifest(self) -> None:
        self._print_header("PHASE 5: Manifest")

        entries: List[Dict] = []
        for kind, path in sorted(self._report_paths.items()):
            sha256 = self._file_sha256(path) if not self.dry_run else "(dry-run)"
            entry = {
                "filename": path.name,
                "path": str(path),
                "label": kind,
                "sha256": sha256,
                "sizeBytes": path.stat().st_size if not self.dry_run else 0,
            }
            entries.append(entry)
            display = sha256[:16] + "..." if sha256 and sha256 != "(dry-run)" else str(sha256)
            ptprint(f"  ✓ {path.name}: {display}", "OK", condition=self._out())

        self._add_node("manifest", True,
                       generatedAt=datetime.now(timezone.utc).isoformat(),
                       fileCount=len(entries),
                       files=entries)

    def run_gate(self) -> None:
        if not self.discover_reports():
            self.ptjsonlib.set_status("finished")
            return
        self.validate_chain()

        cv_result = "PASS" if self._cross_valid else "FAIL"
        cv_level = "OK" if self._cross_valid else "ERROR"
        action = f"CoC gate [{self.scenario}] - cross-validation: {cv_result}"

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012", "NIST SP 800-61 Rev. 3"],
            "mode": MODE_GATE,
            "scenario": self.scenario,
            "crossValidated": self._cross_valid,
            "verificationStatus": self._ver_status,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": action,
                "result": "SUCCESS" if self._cross_valid else "VALIDATION_FAILED",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        self._print_header("GATE SUMMARY")
        ptprint(f"Case: {self.case_id}  |  Scenario: {self.scenario}",
                "TEXT", condition=self._out())
        ptprint(f"Cross-validation: {cv_result}", cv_level, condition=self._out())
        if not self._cross_valid:
            ptprint("⚠ Gate FAILED - do not proceed with analysis phase",
                    "WARNING", condition=self._out(), colortext=True)
        else:
            ptprint("✓ Gate PASSED - safe to proceed with analysis phase",
                    "OK", condition=self._out(), colortext=True)
        ptprint("=" * 70, "TITLE", condition=self._out())

    def run_consolidate(self) -> None:
        if not self.discover_reports():
            self.ptjsonlib.set_status("finished")
            return
        self.validate_chain()
        timeline = self.build_timeline()
        self.generate_coc_documentation()
        self.generate_manifest()

        cv_result = "PASS" if self._cross_valid else "FAIL"
        cv_level = "OK" if self._cross_valid else "ERROR"
        action = (f"CoC consolidation [{self.scenario}] - {len(self._reports)} reports, "
                  f"{len(timeline)} timeline entries, cross-validation: {cv_result}")

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012", "NIST SP 800-61 Rev. 3"],
            "mode": MODE_CONSOLIDATE,
            "scenario": self.scenario,
            "storageLocation": self.storage_location or "",
            "crossValidated": self._cross_valid,
            "verificationStatus": self._ver_status,
            "reportCount": len(self._reports),
            "timelineEntryCount": len(timeline),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": action,
                "result": "SUCCESS" if self._cross_valid else "VALIDATION_FAILED",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        self._print_header("CONSOLIDATION SUMMARY")
        ptprint(f"Case: {self.case_id}  |  Scenario: {self.scenario}",
                "TEXT", condition=self._out())
        ptprint(f"Reports consolidated: {len(self._reports)}", "TEXT", condition=self._out())
        ptprint(f"Timeline entries: {len(timeline)}", "TEXT", condition=self._out())
        ptprint(f"Cross-validation: {cv_result}", cv_level, condition=self._out())
        if self.storage_location:
            ptprint(f"Storage: {self.storage_location}", "TEXT", condition=self._out())
        if self.scenario == SCENARIO_MALWARE and self.incident_type:
            ptprint(f"Incident: {self.incident_type}", "TEXT", condition=self._out())
        if not self._cross_valid:
            ptprint("⚠ Cross-validation failed - master CoC document marked as invalid",
                    "WARNING", condition=self._out(), colortext=True)
        ptprint("=" * 70, "TITLE", condition=self._out())

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"COC MANAGER v{__version__}  |  Case: {self.case_id}  |  "
                f"Mode: {self.mode}  |  Scenario: {self.scenario}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if self.mode == MODE_GATE:
            self.run_gate()
        else:
            self.run_consolidate()
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
            "Universal Chain of Custody manager - gate + consolidate modes",
            "  gate:        Early cross-validation after image acquisition (fast gate)",
            "  consolidate: Final consolidation of ALL workflow reports + master CoC",
            "Auto-discovers JSON reports in --output-dir when paths are not provided.",
            "Scenario auto-detected from case-id prefix (COC / PHOTORECOVERY / MALWARE).",
            "Compliant with NIST SP 800-86, ISO/IEC 27037:2012, NIST SP 800-61 Rev. 3.",
        ]},
        {"usage": ["ptcocmanager <case-id> [--mode gate|consolidate] [options]"]},
        {"usage_example": [
            "ptcocmanager COC-2025-01-26-001 --mode gate",
            "ptcocmanager COC-2025-01-26-001 --mode consolidate --storage-location 'Room B03'",
            "ptcocmanager PHOTORECOVERY-2025-01-26-001 --mode gate",
            "ptcocmanager PHOTORECOVERY-2025-01-26-001 --mode consolidate --client-data 'Client X'",
            "ptcocmanager MALWARE-2025-01-26-001 --mode gate",
            "ptcocmanager MALWARE-2025-01-26-001 --mode consolidate --incident-type ransomware",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["", "--mode", "<m>", f"Operation mode: {' | '.join(MODES)} (default: consolidate)"],
            ["", "--scenario", "<s>", f"Force scenario: {', '.join(SCENARIOS)} (default: auto)"],
            ["-i", "--imaging-json", "<f>", "Path to ptforensicimaging JSON (default: auto-discover)"],
            ["-v", "--verification-json", "<f>", "Path to ptimageverification JSON (default: auto-discover)"],
            ["-r", "--readability-json", "<f>", "Path to ptmediareadability JSON (optional)"],
            ["-V", "--volatile-json", "<f>", "Path to ptvolatilecollector JSON (malware, optional)"],
            ["-s", "--storage-location", "<s>", "Physical storage location (chain-of-custody)"],
            ["-c", "--client-data", "<s>", "Client name + GDPR basis (photo-recovery)"],
            ["-T", "--incident-type", "<s>", "Incident type (malware: ransomware/APT/insider)"],
            ["-A", "--affected-system", "<s>", "Affected system hostname/IP/OS (malware)"],
            ["-D", "--detection-time", "<iso>", "Detection timestamp ISO 8601 (malware)"],
            ["-I", "--isolation-time", "<iso>", "Isolation timestamp ISO 8601 (malware)"],
            ["-o", "--output-dir", "<d>", f"Auto-discovery search dir (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["", "--dry-run", "", "Simulate without reading files"],
            ["-h", "--help", "", "Show help"],
            ["", "--version", "", "Show version"],
        ]},
        {"notes": [
            "Exit 0 = SUCCESS | Exit 1 = VALIDATION_FAILED | Exit 99 = error",
            "Gate mode loads imaging+verification+readability only (fast, early in workflow)",
            "Consolidate mode discovers ALL workflow reports + builds chronological timeline",
            "Recommended workflow: gate after image verification, consolidate before handover",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("--mode", choices=list(MODES), default=MODE_CONSOLIDATE)
    parser.add_argument("--scenario", choices=list(SCENARIOS), default=None)
    parser.add_argument("-i", "--imaging-json", default=None)
    parser.add_argument("-v", "--verification-json", default=None)
    parser.add_argument("-r", "--readability-json", default=None)
    parser.add_argument("-V", "--volatile-json", default=None)
    parser.add_argument("-s", "--storage-location", default=None)
    parser.add_argument("-c", "--client-data", default=None)
    parser.add_argument("-T", "--incident-type", default=None)
    parser.add_argument("-A", "--affected-system", default=None)
    parser.add_argument("-D", "--detection-time", default=None)
    parser.add_argument("-I", "--isolation-time", default=None)
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
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
        tool = PtCocManager(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("crossValidated") else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())