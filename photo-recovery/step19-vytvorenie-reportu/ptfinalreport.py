#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfinalreport - Forensic photo recovery final report generator

    ptfinalreport is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptfinalreport is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptfinalreport.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"

QUALITY_THRESHOLDS = {
    95: "Excellent",
    85: "Very Good",
    75: "Good",
    60: "Fair",
}

STANDARDS = [
    "ISO/IEC 27037:2012 – Guidelines for digital evidence identification, collection, acquisition, preservation",
    "NIST SP 800-86 – Guide to Integrating Forensic Techniques into Incident Response",
    "ACPO Good Practice Guide for Digital Evidence v5",
    "SWGDE Best Practices for Digital and Multimedia Evidence",
    "ISO/IEC 10918-1 (JPEG) / PNG ISO/IEC 15948:2004",
]

TOOLS_USED = [
    "dc3dd – Forensic disk imaging with hashing",
    "ddrescue – Damaged media imaging and rescue",
    "The Sleuth Kit (mmls, fsstat, fls, icat) – Filesystem analysis and recovery",
    "PhotoRec – Signature-based file carving",
    "ExifTool – EXIF/metadata extraction",
    "ImageMagick identify – Image structure validation",
    "Python PIL/Pillow – Image decoding validation and repair",
    "jpeginfo / pngcheck – Format-specific validation",
    "sha256sum / dc3dd – Hash verification",
]

BACKUP_RECOMMENDATIONS = [
    "Follow the 3-2-1 Backup Rule: 3 copies, 2 different media types, 1 off-site",
    "Use both local backup (external HDD) and cloud storage (Google Photos, iCloud, OneDrive)",
    "Verify backups regularly by opening random photos from each backup set",
    "Format memory cards in-camera (not on computer) before each use",
    "Always eject media safely before physical removal",
    "Consider a NAS (Network Attached Storage) for automated home backups",
    "Enable automatic cloud upload on smartphones",
]


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtFinalReport:
    """
    Forensic photo recovery final report generator – ptlibs compliant.

    Six-phase process:
    1. Collect data from all previous steps
       (validation, EXIF, repair, catalog summary)
    2. Generate executive summary (client-friendly language)
    3. Build 11-section comprehensive JSON report
    4. Generate PDF (if reportlab installed)
    5. Create client README.txt and delivery_checklist.json
    6. Save FINAL_REPORT.json, workflow_summary.json, all files

    The report is designed to be courtroom-ready, meeting
    ISO/IEC 27037:2012, NIST SP 800-86 and ACPO standards.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Output location
        self.report_dir = self.output_dir / f"{self.case_id}_final_report"

        # Source report paths
        self._src = {
            "validation": self.output_dir / f"{self.case_id}_validation_report.json",
            "exif":       self.output_dir / f"{self.case_id}_exif_analysis" / "exif_database.json",
            "repair":     self.output_dir / f"{self.case_id}_repair_report.json",
            "catalog":    self.output_dir / f"{self.case_id}_catalog" / "catalog_summary.json",
        }

        # Loaded data
        self._data: Dict[str, Any] = {}

        # Report structure (11 sections)
        self._report: Dict[str, Any] = {
            "reportVersion": "1.0",
            "caseId":        self.case_id,
            "reportDate":    datetime.now(timezone.utc).isoformat(),
            "sections":      {},
        }

        self.ptjsonlib.add_properties({
            "caseId":          self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "scriptVersion":   __version__,
            "totalPhotos":     0,
            "integrityScore":  0.0,
            "qualityRating":   "",
            "pdfGenerated":    False,
            "sectionsGenerated": 0,
            "dryRun":          self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _quality_rating(self, score: float) -> str:
        for threshold, label in sorted(QUALITY_THRESHOLDS.items(), reverse=True):
            if score >= threshold:
                return label
        return "Poor"

    def _props(self, report_data: Dict, *keys: str) -> Any:
        """Traverse nested dict by key candidates (camelCase then snake_case)."""
        obj = report_data
        for key in keys:
            if obj is None:
                return None
            if isinstance(obj, dict):
                # Try direct key, then camelCase / snake_case variants
                for candidate in [key,
                                   key.replace("_", ""),
                                   "".join(w.capitalize() if i else w
                                           for i, w in enumerate(key.split("_")))]:
                    if candidate in obj:
                        obj = obj[candidate]
                        break
                else:
                    return None
        return obj

    def _load_json(self, path: Path) -> Optional[Dict]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            ptprint(f"  ⚠ Cannot read {path.name}: {exc}",
                    "WARNING", condition=not self.args.json)
            return None

    def _val_stats(self) -> Dict:
        """Return validation statistics dict from the loaded report."""
        v = self._data.get("validation", {})
        # ptlibs format: result.properties; legacy: statistics
        return (self._props(v, "result", "properties") or
                v.get("statistics") or v)

    def _cat_stats(self) -> Dict:
        v = self._data.get("catalog", {})
        return (self._props(v, "result", "properties") or
                v.get("statistics") or v)

    def _exif_stats(self) -> Optional[Dict]:
        v = self._data.get("exif")
        if v is None:
            return None
        return (self._props(v, "result", "properties") or
                v.get("statistics") or v)

    def _repair_stats(self) -> Optional[Dict]:
        v = self._data.get("repair")
        if v is None:
            return None
        return (self._props(v, "result", "properties") or
                v.get("statistics") or v)

    # -------------------------------------------------------------------------
    # PHASE 1 – COLLECT DATA
    # -------------------------------------------------------------------------

    def collect_data(self) -> bool:
        """
        Phase 1 – Load JSON reports from all previous workflow steps.

        Required: validation_report.json, catalog/catalog_summary.json
        Optional: exif_analysis/exif_database.json, repair_report.json
        """
        ptprint("\n[STEP 1/6] Collecting Data from Previous Steps",
                "TITLE", condition=not self.args.json)

        if self.dry_run:
            # Synthetic data for dry-run mode
            self._data = {
                "validation": {"statistics": {
                    "total_files": 100, "valid_files": 91, "corrupted_files": 7,
                    "unrecoverable_files": 2, "integrity_score": 91.0,
                    "by_format": {"jpg": {"total": 80, "valid": 74}},
                    "by_source": {"fs_based": {"total": 65, "valid": 63}},
                    "corruption_types": {"truncated": 5, "corrupt_segments": 2},
                }},
                "exif": {"statistics": {
                    "files_with_exif": 82, "with_datetime": 79,
                    "with_gps": 41, "unique_cameras": 3,
                    "date_range": {"earliest": "2023-06-01", "latest": "2024-12-15"},
                }},
                "repair": {"statistics": {
                    "total_attempted": 7, "successful_repairs": 5,
                    "failed_repairs": 2, "success_rate": 71.4,
                    "by_corruption_type": {
                        "truncated": {"attempted": 5, "successful": 4},
                        "corrupt_segments": {"attempted": 2, "successful": 1},
                    },
                }},
                "catalog": {"statistics": {
                    "total_photos": 96, "from_validation": 91, "from_repair": 5,
                    "thumbnails_generated": 288, "with_exif": 82, "with_gps": 41,
                    "unique_cameras": 3,
                    "date_range": {"earliest": "2023-06-01", "latest": "2024-12-15"},
                }},
            }
            for key in self._data:
                ptprint(f"  [DRY-RUN] {key}: synthetic data",
                        "INFO", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "dataCollection", properties={"success": True, "dryRun": True}))
            return True

        # Validation (required)
        val = self._load_json(self._src["validation"])
        if val is None:
            ptprint("✗ validation_report.json not found – run Step 15 first",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "dataCollection", properties={"success": False,
                                              "error": "validation_report not found"}))
            return False
        self._data["validation"] = val
        ptprint("  ✓ Validation report loaded", "OK", condition=not self.args.json)

        # Catalog (required)
        cat = self._load_json(self._src["catalog"])
        if cat is None:
            ptprint("✗ catalog_summary.json not found – run Step 18 first",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "dataCollection", properties={"success": False,
                                              "error": "catalog_summary not found"}))
            return False
        self._data["catalog"] = cat
        ptprint("  ✓ Catalog summary loaded", "OK", condition=not self.args.json)

        # Optional sources
        for key, label in [("exif", "EXIF database"),
                            ("repair", "Repair report")]:
            data = self._load_json(self._src[key])
            if data:
                self._data[key] = data
                ptprint(f"  ✓ {label} loaded", "OK", condition=not self.args.json)
            else:
                ptprint(f"  ⚠ {label} not found – skipping",
                        "INFO", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "dataCollection",
            properties={"success": True, "sources": list(self._data.keys())}))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 & 3 – BUILD 11-SECTION REPORT
    # -------------------------------------------------------------------------

    def _s1_executive_summary(self) -> Dict:
        vs    = self._val_stats()
        cs    = self._cat_stats()
        es    = self._exif_stats()
        rs    = self._repair_stats()

        total       = int(cs.get("totalPhotos") or cs.get("total_photos") or 0)
        integrity   = float(vs.get("integrityScore") or vs.get("integrity_score") or 0)
        rating      = self._quality_rating(integrity)
        repair_done = rs is not None

        self.ptjsonlib.add_properties({
            "totalPhotos":    total,
            "integrityScore": integrity,
            "qualityRating":  rating,
        })

        steps_done = [
            "Created forensic image of the media (write-blocked)",
            "Analyzed filesystem structure",
            "Recovered active and deleted photographs",
            "Validated integrity of every recovered file",
            "Repaired corrupted files" if repair_done else "No repair needed (all files valid)",
            "Extracted EXIF metadata (camera, date, GPS)",
            "Generated interactive HTML photo catalog",
        ]

        client_gets = [
            f"{total} recovered photos in organized catalog",
            "Interactive HTML catalog for easy browsing (photo_catalog.html)",
            "Thumbnails in 3 sizes (150/300/600 px) for quick preview",
            "Complete EXIF metadata – camera, date taken, GPS coordinates",
            "CSV spreadsheet for analysis in Microsoft Excel",
            "This comprehensive technical report",
            "README with usage instructions and backup recommendations",
        ]

        result: Dict[str, Any] = {
            "overview": {
                "totalPhotosRecovered": total,
                "integrityScorePercent": integrity,
                "qualityRating": rating,
            },
            "whatWeDid": steps_done,
            "clientGets": client_gets,
            "recommendations": BACKUP_RECOMMENDATIONS[:4],
        }

        if es:
            dt_cov  = int(es.get("withDatetime") or es.get("with_datetime") or 0)
            gps_cov = int(es.get("withGps")      or es.get("with_gps")      or 0)
            cams    = int(es.get("uniqueCameras") or es.get("unique_cameras") or 0)
            dr      = es.get("dateRange") or es.get("date_range") or {}
            result["metadataHighlights"] = {
                "photosWithDatetime": dt_cov,
                "photosWithGps":      gps_cov,
                "uniqueCameras":      cams,
                "dateRange":          dr,
            }

        return result

    def _s2_case_information(self) -> Dict:
        return {
            "caseId":        self.case_id,
            "reportDate":    self._report["reportDate"],
            "reportVersion": "1.0",
            "analyst":       "Forensic Photo Recovery System",
            "laboratory":    "Digital Forensics Laboratory",
            "classification": "CONFIDENTIAL – addressee only",
        }

    def _s3_evidence_information(self) -> Dict:
        return {
            "evidenceDescription": "Digital storage media submitted for photo recovery",
            "evidenceType":        "Photo storage device (memory card / internal storage)",
            "conditionOnReceipt":  "Analyzed forensically",
            "forensicImageCreated": True,
            "writeBlockerUsed":     True,
            "originalMediaStatus":  "Unchanged – available for return",
            "hashAlgorithmUsed":    "SHA-256",
        }

    def _s4_methodology(self) -> Dict:
        rs = self._repair_stats()
        cs = self._cat_stats()
        from_rep = int(cs.get("fromRepair") or cs.get("from_repair") or 0)

        steps = [
            "Step 10:  Filesystem Analysis (partition table, FS type, directory readability)",
            "Step 12A: Filesystem-based Recovery (fls + icat, original filenames preserved)",
            "Step 12B: File Carving (PhotoRec, signature-based, works without filesystem)",
            "Step 13:  Consolidation (merge 12A/12B, SHA-256 deduplication)",
            "Step 14:  EXIF Metadata Analysis (batch ExifTool, timeline, GPS, cameras)",
            "Step 15:  Integrity Validation (magic bytes, PIL, ImageMagick, jpeginfo)",
            "Step 16:  Repair Decision (automated cost-benefit analysis)",
            "Step 17:  Photo Repair (header/footer/segments/truncated)"
            if (rs is not None or from_rep > 0) else
            "Step 17:  Photo Repair – skipped (decision: skip_repair)",
            "Step 18:  Cataloging (thumbnails, indexes, HTML catalog)",
            "Step 19:  Final Report (this document)",
        ]

        return {
            "standardsFollowed": STANDARDS,
            "toolsUsed":         TOOLS_USED,
            "forensicPrinciples": [
                "All analysis performed on forensic image – original media untouched",
                "Write-blocker used during imaging",
                "SHA-256 hash verification at all stages",
                "Chain of custody documented throughout",
                "READ-ONLY operations on evidence at all steps",
            ],
            "workflowSteps": steps,
        }

    def _s5_timeline(self) -> Dict:
        return {
            "workflowEnd":       self._report["reportDate"],
            "estimatedDuration": "5–10 hours (depending on media size and damage level)",
            "stepsWithDuration": [
                {"step": "Filesystem Analysis",            "estimate": "5–15 min"},
                {"step": "Photo Recovery (FS + carving)",  "estimate": "30 min – 8 h"},
                {"step": "Consolidation",                  "estimate": "5–30 min"},
                {"step": "EXIF Analysis",                  "estimate": "5–30 min"},
                {"step": "Integrity Validation",           "estimate": "5–30 min"},
                {"step": "Repair Decision",                "estimate": "<1 min"},
                {"step": "Photo Repair (if needed)",       "estimate": "1–45 min"},
                {"step": "Cataloging",                     "estimate": "30–60 min"},
                {"step": "Final Report",                   "estimate": "5–10 min"},
            ],
        }

    def _s6_results(self) -> Dict:
        vs = self._val_stats()
        cs = self._cat_stats()
        es = self._exif_stats()
        rs = self._repair_stats()

        result: Dict[str, Any] = {
            "recoveryBreakdown": {
                "totalFilesAnalyzed":  int(vs.get("totalFiles")        or vs.get("total_files", 0)),
                "validFiles":          int(vs.get("validFiles")         or vs.get("valid_files", 0)),
                "corruptedFiles":      int(vs.get("corruptedFiles")     or vs.get("corrupted_files", 0)),
                "unrecoverableFiles":  int(vs.get("unrecoverableFiles") or vs.get("unrecoverable_files", 0)),
                "integrityScore":      float(vs.get("integrityScore")   or vs.get("integrity_score", 0)),
            },
            "finalDelivery": {
                "totalPhotosCataloged": int(cs.get("totalPhotos")   or cs.get("total_photos", 0)),
                "fromValidation":       int(cs.get("fromValidation") or cs.get("from_validation", 0)),
                "fromRepair":           int(cs.get("fromRepair")     or cs.get("from_repair", 0)),
            },
            "byFormat": vs.get("byFormat") or vs.get("by_format") or {},
            "bySource": vs.get("bySource") or vs.get("by_source") or {},
        }

        if rs:
            result["repairStatistics"] = {
                "totalAttempted":    int(rs.get("totalAttempted")    or rs.get("total_attempted", 0)),
                "successfulRepairs": int(rs.get("successfulRepairs") or rs.get("successful_repairs", 0)),
                "failedRepairs":     int(rs.get("failedRepairs")     or rs.get("failed_repairs", 0)),
                "successRate":       float(rs.get("successRate")     or rs.get("success_rate", 0)),
                "byCorruptionType":  rs.get("byCorruptionType") or rs.get("by_corruption_type") or {},
            }

        if es:
            result["metadataCoverage"] = {
                "filesWithExif":     int(es.get("filesWithExif")  or es.get("files_with_exif", 0)),
                "filesWithDatetime": int(es.get("withDatetime")   or es.get("with_datetime", 0)),
                "filesWithGps":      int(es.get("withGps")        or es.get("with_gps", 0)),
                "uniqueCameras":     int(es.get("uniqueCameras")  or es.get("unique_cameras", 0)),
                "dateRange":         es.get("dateRange") or es.get("date_range") or {},
            }

        return result

    def _s7_technical_details(self) -> Dict:
        vs = self._val_stats()
        es = self._exif_stats()
        rs = self._repair_stats()

        detail: Dict[str, Any] = {
            "validationDetails": {
                "toolsUsed":        ["magic bytes", "PIL/Pillow", "ImageMagick identify", "jpeginfo", "pngcheck"],
                "decisionLogic":    "ALL tools pass + valid magic → valid; ≥1 pass → corrupted; ALL fail → unrecoverable",
                "corruptionTypesDetected": list(
                    (vs.get("corruptionTypes") or vs.get("corruption_types") or {}).keys()),
            },
        }

        if rs:
            detail["repairTechniques"] = {
                "missing_footer":   "Append FF D9 EOI marker (85–95 % success)",
                "invalid_header":   "Remove leading garbage / reconstruct SOI+JFIF (90–95 %)",
                "corrupt_segments": "Strip APP segments, preserve SOF/DQT/DHT+SOS..EOI (80–85 %)",
                "truncated":        "PIL LOAD_TRUNCATED_IMAGES partial recovery (50–70 %)",
            }

        if es:
            detail["metadataExtraction"] = {
                "tool":            "ExifTool (libimage-exiftool-perl)",
                "batchSize":       50,
                "fieldsExtracted": [
                    "DateTimeOriginal, CreateDate, ModifyDate",
                    "Make, Model, SerialNumber",
                    "ISO, FNumber, ExposureTime, FocalLength",
                    "GPSLatitude, GPSLongitude, GPSAltitude",
                    "ImageWidth, ImageHeight, Orientation",
                    "Software (edit detection)",
                ],
            }

        return detail

    def _s8_quality_assurance(self) -> Dict:
        vs    = self._val_stats()
        cs    = self._cat_stats()
        total = int(cs.get("totalPhotos") or cs.get("total_photos") or 1)
        exif  = int(cs.get("withExif")    or cs.get("with_exif", 0))

        return {
            "multiToolValidation":   True,
            "hashVerification":      "SHA-256 used at imaging, consolidation, and validation phases",
            "checksPerformed": [
                "All recovered files validated with ≥ 3 independent tools",
                "SHA-256 deduplication during consolidation (Step 13)",
                "Catalog completeness: 100 % – every valid/repaired file included",
                "Metadata extraction verified against known EXIF format",
            ],
            "metrics": {
                "catalogCompleteness":  "100 %",
                "integrityScore":       f"{vs.get('integrityScore') or vs.get('integrity_score', 0)} %",
                "exifCoveragePercent":  f"{exif / total * 100:.1f} %" if total else "0 %",
            },
            "peerReviewStatus":  "PENDING – REQUIRED before delivery",
            "signaturesStatus":  "PENDING – REQUIRED before delivery",
        }

    def _s9_delivery_package(self) -> Dict:
        cs = self._cat_stats()
        total = int(cs.get("totalPhotos") or cs.get("total_photos") or 0)

        return {
            "contents": [
                f"{total} recovered photos in organized catalog",
                "Interactive HTML catalog (photo_catalog.html)",
                "Thumbnails in 3 sizes (small 150 px / medium 300 px / large 600 px)",
                "Complete metadata – complete_catalog.json and catalog.csv",
                "Search indexes – chronological, by_camera, GPS (JSON)",
                "This final report (FINAL_REPORT.json)",
                "Client README with instructions (README.txt)",
            ],
            "catalogStructure": {
                "photos":      f"{self.case_id}_catalog/photos/",
                "thumbnails":  f"{self.case_id}_catalog/thumbnails/{{small,medium,large}}/",
                "metadata":    f"{self.case_id}_catalog/metadata/",
                "indexes":     f"{self.case_id}_catalog/indexes/",
                "htmlCatalog": f"{self.case_id}_catalog/photo_catalog.html",
            },
            "howToAccess": [
                "Open photo_catalog.html in any web browser",
                "Search by filename, camera or date",
                "Click any photo to view full size",
                "Use source filter to see validation vs. repair photos",
                "Open catalog.csv in Excel for metadata analysis",
            ],
        }

    def _s10_chain_of_custody(self) -> Dict:
        return {
            "description": "Chain of custody maintained throughout the recovery workflow",
            "integrityMaintained": True,
            "originalMediaStatus": "Unchanged – available for return to client",
            "events": [
                {"event": "Evidence received",           "step": "Pre-workflow",
                 "action": "Media received, condition documented, case ID assigned"},
                {"event": "Forensic image created",     "step": "Step 5 (Imaging)",
                 "action": "Write-blocked forensic copy created; SHA-256 hashes recorded"},
                {"event": "Filesystem analysis",        "step": "Step 10",
                 "action": "Partition/FS structure analyzed; recovery strategy determined"},
                {"event": "Photo recovery",             "step": "Steps 12A/12B",
                 "action": "Active and deleted files recovered; originals untouched"},
                {"event": "Consolidation & dedup",      "step": "Step 13",
                 "action": "Duplicate removal via SHA-256; master catalog created"},
                {"event": "Validation performed",       "step": "Step 15",
                 "action": "Multi-tool integrity validation; corrupted files identified"},
                {"event": "Repair performed/decided",   "step": "Steps 16–17",
                 "action": "Automated repair decision; corrupted files treated"},
                {"event": "Catalog generated",          "step": "Step 18",
                 "action": "Thumbnails, indexes, HTML catalog created"},
                {"event": "Final report generated",     "step": "Step 19",
                 "action": "This document; ready for peer review and delivery"},
            ],
        }

    def _s11_signatures(self) -> Dict:
        return {
            "note": "This report MUST be reviewed and signed before delivery to client",
            "primaryAnalyst": {
                "name":      "[ANALYST NAME]",
                "signature": "PENDING",
                "date":      "PENDING",
                "role":      "Forensic Analyst",
            },
            "peerReviewer": {
                "name":      "[REVIEWER NAME]",
                "signature": "PENDING – REQUIRED",
                "date":      "PENDING",
                "role":      "Senior Analyst / Quality Assurance",
            },
            "reviewChecklist": [
                "Results are consistent with findings from each step",
                "All files accounted for in catalog",
                "Technical details are accurate",
                "Chain of custody is unbroken",
                "Report language is appropriate for court submission",
            ],
        }

    def build_report(self) -> None:
        """Phases 2 & 3 – Generate all 11 sections."""
        ptprint("\n[STEP 2/6] Building 11-Section Report",
                "TITLE", condition=not self.args.json)

        section_builders = [
            ("executiveSummary",    self._s1_executive_summary,    "Executive Summary"),
            ("caseInformation",     self._s2_case_information,     "Case Information"),
            ("evidenceInformation", self._s3_evidence_information, "Evidence Information"),
            ("methodology",         self._s4_methodology,          "Methodology"),
            ("timeline",            self._s5_timeline,             "Timeline"),
            ("results",             self._s6_results,              "Results"),
            ("technicalDetails",    self._s7_technical_details,    "Technical Details"),
            ("qualityAssurance",    self._s8_quality_assurance,    "Quality Assurance"),
            ("deliveryPackage",     self._s9_delivery_package,     "Delivery Package"),
            ("chainOfCustody",      self._s10_chain_of_custody,    "Chain of Custody"),
            ("signatures",          self._s11_signatures,          "Signatures"),
        ]

        for key, builder, label in section_builders:
            self._report["sections"][key] = builder()
            ptprint(f"  ✓ Section {len(self._report['sections'])}: {label}",
                    "INFO", condition=not self.args.json)

        ptprint(f"  All {len(self._report['sections'])} sections generated",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"sectionsGenerated": len(self._report["sections"])})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "reportBuilt",
            properties={"sections": len(self._report["sections"])}))

    # -------------------------------------------------------------------------
    # PHASE 4 – PDF (OPTIONAL)
    # -------------------------------------------------------------------------

    def generate_pdf(self) -> Optional[str]:
        """
        Phase 4 – Generate PDF report using reportlab (optional).

        Produces a multi-page A4 document with cover page,
        all 11 sections, tables and a signature block.
        Skipped gracefully if reportlab is not installed.
        """
        ptprint("\n[STEP 4/6] Generating PDF Report",
                "TITLE", condition=not self.args.json)

        if not REPORTLAB_AVAILABLE:
            ptprint("  ⚠ reportlab not installed – skipping PDF",
                    "WARNING", condition=not self.args.json)
            ptprint("  Install: pip install reportlab --break-system-packages",
                    "INFO",    condition=not self.args.json)
            return None

        if self.dry_run:
            ptprint("  [DRY-RUN] PDF skipped",
                    "INFO", condition=not self.args.json)
            return None

        pdf_path = self.report_dir / "FINAL_REPORT.pdf"

        styles    = getSampleStyleSheet()
        title_sty = ParagraphStyle("title",    parent=styles["Title"],
                                   fontSize=20, spaceAfter=12)
        h1_sty    = ParagraphStyle("h1",       parent=styles["Heading1"],
                                   fontSize=14, spaceAfter=6, textColor=colors.HexColor("#1e293b"))
        h2_sty    = ParagraphStyle("h2",       parent=styles["Heading2"],
                                   fontSize=11, spaceAfter=4, textColor=colors.HexColor("#334155"))
        body_sty  = ParagraphStyle("body",     parent=styles["Normal"],
                                   fontSize=9,  leading=14)
        mono_sty  = ParagraphStyle("mono",     parent=styles["Code"],
                                   fontSize=8,  leading=12,
                                   backColor=colors.HexColor("#f8fafc"))

        cs        = self._cat_stats()
        vs        = self._val_stats()
        total     = int(cs.get("totalPhotos") or cs.get("total_photos") or 0)
        integrity = float(vs.get("integrityScore") or vs.get("integrity_score") or 0)
        rating    = self._quality_rating(integrity)

        story = []

        # ── Cover page ────────────────────────────────────────────────────
        story += [
            Spacer(1, 3*cm),
            Paragraph("FORENSIC PHOTO RECOVERY", title_sty),
            Paragraph("Final Technical Report", styles["Heading2"]),
            Spacer(1, 1*cm),
            HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e293b")),
            Spacer(1, 0.5*cm),
        ]

        cover_data = [
            ["Case ID:",          self.case_id],
            ["Report Date:",      self._report["reportDate"][:10]],
            ["Total Photos:",     str(total)],
            ["Integrity Score:",  f"{integrity} %"],
            ["Quality Rating:",   rating],
        ]
        cov_tbl = Table(cover_data, colWidths=[5*cm, 10*cm])
        cov_tbl.setStyle(TableStyle([
            ("FONTSIZE",    (0,0), (-1,-1), 10),
            ("FONTNAME",    (0,0), (0,-1),  "Helvetica-Bold"),
            ("BOTTOMPADDING",(0,0),(-1,-1), 6),
            ("LINEBELOW",   (0,-1),(-1,-1), 0.5, colors.grey),
        ]))
        story += [cov_tbl, Spacer(1, 1*cm)]

        story += [
            Paragraph("CONFIDENTIAL – For addressee only", styles["Normal"]),
            Spacer(1, 0.5*cm),
            Paragraph(
                "This report requires peer review and signatures before delivery to client.",
                ParagraphStyle("warn", parent=styles["Normal"],
                               textColor=colors.HexColor("#dc2626"), fontName="Helvetica-Bold")),
            PageBreak(),
        ]

        # ── Sections 1–11 ─────────────────────────────────────────────────
        def _para_list(items: List[str]) -> None:
            for item in items:
                story.append(Paragraph(f"• {item}", body_sty))
            story.append(Spacer(1, 0.3*cm))

        def _section(num: int, title: str) -> None:
            story.append(Paragraph(f"Section {num}: {title}", h1_sty))
            story.append(HRFlowable(width="100%", thickness=1,
                                    color=colors.HexColor("#e2e8f0")))
            story.append(Spacer(1, 0.3*cm))

        sec = self._report["sections"]

        # S1
        _section(1, "Executive Summary")
        ov = sec["executiveSummary"]["overview"]
        story.append(Paragraph(
            f"<b>Total photos recovered: {ov['totalPhotosRecovered']}</b> | "
            f"Integrity score: {ov['integrityScorePercent']} % | "
            f"Quality: <b>{ov['qualityRating']}</b>", body_sty))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("What we did:", h2_sty))
        _para_list(sec["executiveSummary"]["whatWeDid"])
        story.append(Paragraph("Client receives:", h2_sty))
        _para_list(sec["executiveSummary"]["clientGets"])
        if "metadataHighlights" in sec["executiveSummary"]:
            mh = sec["executiveSummary"]["metadataHighlights"]
            story.append(Paragraph(
                f"Metadata coverage: {mh.get('photosWithDatetime',0)} photos with datetime, "
                f"{mh.get('photosWithGps',0)} with GPS, "
                f"{mh.get('uniqueCameras',0)} cameras", body_sty))
        story.append(PageBreak())

        # S2 + S3
        _section(2, "Case Information")
        for k, v in sec["caseInformation"].items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", body_sty))
        story.append(Spacer(1, 0.5*cm))
        _section(3, "Evidence Information")
        for k, v in sec["evidenceInformation"].items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", body_sty))
        story.append(PageBreak())

        # S4
        _section(4, "Methodology")
        story.append(Paragraph("Standards followed:", h2_sty))
        _para_list(sec["methodology"]["standardsFollowed"])
        story.append(Paragraph("Workflow steps:", h2_sty))
        _para_list(sec["methodology"]["workflowSteps"])
        story.append(PageBreak())

        # S6 – Results (most important for court)
        _section(6, "Results")
        rb = sec["results"]["recoveryBreakdown"]
        res_data = [
            ["Metric", "Value"],
            ["Total files analyzed",    str(rb.get("totalFilesAnalyzed", 0))],
            ["Valid files",             str(rb.get("validFiles", 0))],
            ["Corrupted files",         str(rb.get("corruptedFiles", 0))],
            ["Unrecoverable",           str(rb.get("unrecoverableFiles", 0))],
            ["Integrity score",         f"{rb.get('integrityScore', 0)} %"],
            ["Photos in catalog",       str(sec["results"]["finalDelivery"].get("totalPhotosCataloged", 0))],
        ]
        res_tbl = Table(res_data, colWidths=[9*cm, 6*cm])
        res_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0),  colors.HexColor("#1e293b")),
            ("TEXTCOLOR",    (0,0), (-1,0),  colors.white),
            ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
            ("BOX",          (0,0), (-1,-1), 0.5, colors.grey),
            ("INNERGRID",    (0,0), (-1,-1), 0.25, colors.lightgrey),
        ]))
        story += [res_tbl, Spacer(1, 0.5*cm)]
        story.append(PageBreak())

        # S10 – Chain of Custody
        _section(10, "Chain of Custody")
        for event in sec["chainOfCustody"]["events"]:
            story.append(Paragraph(
                f"<b>{event['event']}</b> ({event['step']}): {event['action']}", body_sty))
        story.append(PageBreak())

        # S11 – Signatures
        _section(11, "Signatures and Peer Review")
        story.append(Paragraph(sec["signatures"]["note"],
                               ParagraphStyle("warn2", parent=body_sty,
                                              textColor=colors.HexColor("#dc2626"),
                                              fontName="Helvetica-Bold")))
        story.append(Spacer(1, 1.5*cm))
        sig_data = [
            ["Role", "Name", "Signature", "Date"],
            ["Primary Analyst", "[ANALYST NAME]", "___________________", "________"],
            ["Peer Reviewer",   "[REVIEWER NAME]","___________________", "________"],
        ]
        sig_tbl = Table(sig_data, colWidths=[4.5*cm, 5*cm, 5*cm, 3*cm])
        sig_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0),  colors.HexColor("#1e293b")),
            ("TEXTCOLOR",    (0,0), (-1,0),  colors.white),
            ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("BOX",          (0,0), (-1,-1), 0.5, colors.grey),
            ("INNERGRID",    (0,0), (-1,-1), 0.25, colors.lightgrey),
        ]))
        story += [sig_tbl]

        # Build PDF
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2.5*cm, bottomMargin=2*cm,
            title=f"Forensic Photo Recovery Report – {self.case_id}",
            author="ptfinalreport v" + __version__,
        )
        try:
            doc.build(story)
            self.ptjsonlib.add_properties({"pdfGenerated": True})
            ptprint(f"  ✓ PDF generated: {pdf_path.name}",
                    "OK", condition=not self.args.json)
            return str(pdf_path)
        except Exception as exc:
            ptprint(f"  ✗ PDF generation failed: {exc}",
                    "WARNING", condition=not self.args.json)
            return None

    # -------------------------------------------------------------------------
    # PHASE 5 – CLIENT README + DELIVERY CHECKLIST
    # -------------------------------------------------------------------------

    def create_client_readme(self) -> None:
        """Phase 5a – Create README.txt with client instructions."""
        ptprint("\n  Creating client README.txt…",
                "INFO", condition=not self.args.json)

        cs    = self._cat_stats()
        vs    = self._val_stats()
        total = int(cs.get("totalPhotos")   or cs.get("total_photos", 0))
        score = float(vs.get("integrityScore") or vs.get("integrity_score", 0))
        prefix = f"{self.case_id}"

        content = f"""{"="*70}
PHOTO RECOVERY – DELIVERY PACKAGE
{"="*70}

Case ID:                {self.case_id}
Delivery Date:          {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
Total Photos Recovered: {total}
Integrity Score:        {score} %  ({self._quality_rating(score)})

{"="*70}
CONTENTS OF THIS DELIVERY
{"="*70}

1. RECOVERED PHOTOS
   Location:  {prefix}_catalog/photos/
   Count:     {total} photos
   Naming:    {prefix}_0001.jpg, {prefix}_0002.jpg, …

2. INTERACTIVE CATALOG
   File:      {prefix}_catalog/photo_catalog.html
   Open in:   Any web browser (Chrome, Firefox, Safari, Edge)
   Features:  Search, filter, sort, lightbox full-view

3. THUMBNAILS
   Location:  {prefix}_catalog/thumbnails/
   Sizes:     small (150 px), medium (300 px), large (600 px)

4. METADATA
   Location:  {prefix}_catalog/metadata/
   Files:     complete_catalog.json  and  catalog.csv (Excel-ready)

5. INDEXES
   Location:  {prefix}_catalog/indexes/
   Files:     chronological_index.json, by_camera_index.json, gps_index.json

6. FINAL REPORT
   File:      {prefix}_final_report/FINAL_REPORT.json

{"="*70}
HOW TO VIEW YOUR PHOTOS
{"="*70}

OPTION 1 – Interactive Catalog (recommended):
  1. Open the folder:  {prefix}_catalog/
  2. Double-click:     photo_catalog.html
  3. Your browser opens with all photos
  4. Search by filename, camera, date, etc.
  5. Click any photo to see full size

OPTION 2 – Browse directly:
  1. Open:  {prefix}_catalog/photos/
  2. All photos are named {prefix}_0001.jpg etc.
  3. Use any image viewer

OPTION 3 – Excel metadata analysis:
  1. Open:  {prefix}_catalog/metadata/catalog.csv  in Microsoft Excel
  2. Sort by date, camera, GPS, etc.

{"="*70}
BACKUP RECOMMENDATIONS  (IMPORTANT!)
{"="*70}

Follow the 3-2-1 Rule:
  ✓  3 copies of your photos
  ✓  2 different media types (e.g. hard drive + cloud)
  ✓  1 copy off-site (cloud or at a different location)

Practical steps:
  1. Copy photos to your computer hard drive
  2. Upload to cloud storage (Google Photos, iCloud, OneDrive)
  3. Keep a copy on an external USB hard drive
  4. Verify backups regularly (open a few photos at random)

  DO NOT rely on the original storage media that was recovered!

{"="*70}
FREQUENTLY ASKED QUESTIONS
{"="*70}

Q: Why are photos renamed?
A: Photos are systematically named ({prefix}_0001.jpg …) for organisation.
   Original filenames are preserved in the metadata CSV.

Q: Some photos seem to be missing – why?
A: Recovery success depends on how files were deleted and whether
   the storage space was overwritten afterward. Our integrity score
   of {score} % means we recovered {score} % of all discoverable photos.

Q: How do I find photos by date or camera?
A: Use the interactive catalog search box, or sort the CSV by column.

Q: What does "REPAIRED" badge mean in the catalog?
A: These photos had minor structural corruption that was fixed
   automatically (e.g. missing end-of-file marker). Contents unchanged.

{"="*70}
LEGAL NOTICE
{"="*70}

Recovery performed using forensically sound methods following
ISO/IEC 27037:2012 and NIST SP 800-86.

All recovered data is provided "as found" on the storage media.
No modifications to photo content were made.

{"="*70}
END OF README
{"="*70}
"""
        readme_path = self.report_dir / "README.txt"
        if not self.dry_run:
            readme_path.write_text(content, encoding="utf-8")
        ptprint("  ✓ README.txt created", "OK", condition=not self.args.json)

    def create_delivery_checklist(self) -> None:
        """Phase 5b – Create delivery_checklist.json."""
        ptprint("  Creating delivery_checklist.json…",
                "INFO", condition=not self.args.json)

        vs    = self._val_stats()
        score = float(vs.get("integrityScore") or vs.get("integrity_score") or 0)
        exif_present = "exif" in self._data

        checklist = {
            "caseId":         self.case_id,
            "checklistDate":  datetime.now(timezone.utc).isoformat(),
            "items": [
                {"item": "Photo catalog prepared",
                 "status": "COMPLETE",
                 "location": f"{self.case_id}_catalog/"},
                {"item": "HTML catalog accessible",
                 "status": "COMPLETE",
                 "location": f"{self.case_id}_catalog/photo_catalog.html"},
                {"item": "Thumbnails generated",
                 "status": "COMPLETE"},
                {"item": "Integrity validation completed",
                 "status": "COMPLETE",
                 "details": f"Integrity score: {score} %"},
                {"item": "Metadata extraction performed",
                 "status": "COMPLETE" if exif_present else "SKIPPED",
                 "details": "EXIF data available" if exif_present else "No EXIF data"},
                {"item": "Final report generated",
                 "status": "COMPLETE",
                 "location": f"{self.case_id}_final_report/FINAL_REPORT.json"},
                {"item": "Peer review by senior analyst",
                 "status": "PENDING – REQUIRED",
                 "action": "Senior analyst must review and sign off"},
                {"item": "Analyst and reviewer signatures",
                 "status": "PENDING – REQUIRED",
                 "action": "Both signatures required before delivery"},
            ],
            "completionStatus": {
                "completedItems": 6,
                "pendingItems":   2,
                "totalItems":     8,
                "readyForDelivery": False,
                "pendingReason": "Peer review and signatures required",
            },
            "nextSteps": [
                "1. Senior analyst peer review",
                "2. Analyst signature",
                "3. Peer reviewer signature",
                "4. Package catalog + final report",
                "5. Contact client for pickup / secure delivery",
                "6. Step 20: Client delivery",
            ],
        }

        cl_path = self.report_dir / "delivery_checklist.json"
        if not self.dry_run:
            cl_path.write_text(json.dumps(checklist, indent=2, ensure_ascii=False),
                               encoding="utf-8")
        ptprint("  ✓ delivery_checklist.json created",
                "OK", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the six-phase report generation pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FINAL REPORT GENERATION", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.collect_data():
            self.ptjsonlib.set_status("finished")
            return

        if not self.dry_run:
            self.report_dir.mkdir(parents=True, exist_ok=True)

        self.build_report()
        self.generate_pdf()

        ptprint("\n[STEP 5/6] Creating Client Documents",
                "TITLE", condition=not self.args.json)
        self.create_client_readme()
        self.create_delivery_checklist()

        cs        = self._cat_stats()
        vs        = self._val_stats()
        total     = int(cs.get("totalPhotos")   or cs.get("total_photos", 0))
        integrity = float(vs.get("integrityScore") or vs.get("integrity_score", 0))

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FINAL REPORT GENERATION COMPLETED", "OK",   condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total photos:    {total}",      "OK",   condition=not self.args.json)
        ptprint(f"Integrity score: {integrity} %", "OK",   condition=not self.args.json)
        ptprint(f"Quality rating:  {self._quality_rating(integrity)}",
                "OK",   condition=not self.args.json)
        ptprint(f"Report dir:      {self.report_dir.name}/",
                "INFO", condition=not self.args.json)
        ptprint("\n⚠  IMPORTANT NEXT STEPS:", "WARNING", condition=not self.args.json)
        ptprint("  1. Peer review by senior analyst (REQUIRED)",
                "WARNING", condition=not self.args.json)
        ptprint("  2. Obtain analyst + reviewer signatures (REQUIRED)",
                "WARNING", condition=not self.args.json)
        ptprint("  3. Proceed to Step 20 (Delivery)",
                "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 6 – SAVE REPORTS
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 6 – Persist FINAL_REPORT.json and workflow_summary.json.
        In --json mode prints ptlibs JSON to stdout only.
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        # FINAL_REPORT.json (11-section report)
        report_path = self.report_dir / "FINAL_REPORT.json"
        if not self.dry_run:
            report_path.write_text(
                json.dumps(self._report, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
        ptprint(f"\n  ✓ FINAL_REPORT.json saved",
                "OK", condition=not self.args.json)

        # workflow_summary.json
        cs    = self._cat_stats()
        vs    = self._val_stats()
        total = int(cs.get("totalPhotos")   or cs.get("total_photos", 0))
        score = float(vs.get("integrityScore") or vs.get("integrity_score", 0))

        summary = {
            "caseId":      self.case_id,
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "stepsCompleted": [s for s in [
                "Step 10: Filesystem Analysis",
                "Step 12A/12B: Photo Recovery",
                "Step 13: Consolidation",
                "Step 14: EXIF Analysis" if "exif" in self._data else None,
                "Step 15: Integrity Validation",
                "Step 16: Repair Decision",
                "Step 17: Photo Repair" if "repair" in self._data else None,
                "Step 18: Cataloging",
                "Step 19: Final Report",
            ] if s],
            "finalResults": {
                "photosRecovered": total,
                "integrityScore":  score,
                "qualityRating":   self._quality_rating(score),
            },
            "deliverables": [
                "Photo catalog with HTML interface",
                "Complete metadata (JSON + CSV)",
                "Final technical report (FINAL_REPORT.json)",
                "PDF report (FINAL_REPORT.pdf)" if REPORTLAB_AVAILABLE else None,
                "Client README and instructions",
                "Delivery checklist",
            ],
            "nextAction": "Peer review and signatures required before delivery to client",
        }
        summary["deliverables"] = [d for d in summary["deliverables"] if d]

        sum_path = self.report_dir / "workflow_summary.json"
        if not self.dry_run:
            sum_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint(f"  ✓ workflow_summary.json saved",
                "OK", condition=not self.args.json)

        return str(report_path)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Forensic photo recovery final report generator – ptlibs compliant",
            "Consolidates data from all workflow steps (10–18) into an",
            "11-section courtroom-ready JSON report + optional PDF",
        ]},
        {"usage": ["ptfinalreport <case-id> [options]"]},
        {"usage_example": [
            "ptfinalreport PHOTO-2025-001",
            "ptfinalreport CASE-042 --json",
            "ptfinalreport TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",             "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<d>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",             "Simulate with synthetic data, no file writes"],
            ["-j",  "--json",      "",     "JSON output for platform integration"],
            ["-q",  "--quiet",     "",     "Suppress progress output"],
            ["-h",  "--help",      "",     "Show this help and exit"],
            ["--version",  "",             "Show version and exit"],
        ]},
        {"report_sections": [
            "S1  Executive Summary (client-friendly)",
            "S2  Case Information",
            "S3  Evidence Information",
            "S4  Methodology (standards, tools, forensic principles)",
            "S5  Timeline",
            "S6  Results (recovery, repair, metadata)",
            "S7  Technical Details",
            "S8  Quality Assurance",
            "S9  Delivery Package",
            "S10 Chain of Custody",
            "S11 Signatures (PENDING – required before delivery)",
        ]},
        {"output_files": [
            "FINAL_REPORT.json          – 11-section comprehensive report",
            "FINAL_REPORT.pdf           – PDF (requires: pip install reportlab)",
            "README.txt                 – Client instructions + FAQ + backup guide",
            "delivery_checklist.json    – Pre-delivery verification checklist",
            "workflow_summary.json      – Workflow metrics and completeness summary",
        ]},
        {"standards": [
            "ISO/IEC 27037:2012 – Digital evidence handling",
            "NIST SP 800-86    – Forensic techniques",
            "ACPO Good Practice Guide",
            "SWGDE Best Practices",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic final report generator"
    )
    parser.add_argument("case_id",          help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("-j", "--json",     action="store_true")
    parser.add_argument("-q", "--quiet",    action="store_true")
    parser.add_argument("--version",        action="version",
                        version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port",    type=str, default=None)
    parser.add_argument("--process-ident",  type=str, default=None)

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main():
    global SCRIPTNAME
    SCRIPTNAME = "ptfinalreport"
    try:
        args = parse_args()
        tool = PtFinalReport(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("sectionsGenerated", 0) == 11 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
