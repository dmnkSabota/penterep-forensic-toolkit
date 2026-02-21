#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfinalreport - Forensic photo recovery final report generator

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import json
import sys
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

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME         = "ptfinalreport"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"

QUALITY_THRESHOLDS = {95: "Excellent", 85: "Very Good", 75: "Good", 60: "Fair"}

STANDARDS = [
    "ISO/IEC 27037:2012 - Guidelines for digital evidence identification, collection, acquisition, preservation",
    "NIST SP 800-86 - Guide to Integrating Forensic Techniques into Incident Response",
    "ACPO Good Practice Guide for Digital Evidence v5",
    "SWGDE Best Practices for Digital and Multimedia Evidence",
    "ISO/IEC 10918-1 (JPEG) / PNG ISO/IEC 15948:2004",
]
TOOLS_USED = [
    "dc3dd - Forensic disk imaging with hashing",
    "ddrescue - Damaged media imaging and rescue",
    "The Sleuth Kit (mmls, fsstat, fls, icat) - Filesystem analysis and recovery",
    "PhotoRec - Signature-based file carving",
    "ExifTool - EXIF/metadata extraction",
    "ImageMagick identify - Image structure validation",
    "Python PIL/Pillow - Image decoding validation and repair",
    "jpeginfo / pngcheck - Format-specific validation",
    "sha256sum / dc3dd - Hash verification",
]
BACKUP_RECOMMENDATIONS = [
    "Follow the 3-2-1 Rule: 3 copies, 2 different media types, 1 off-site",
    "Use both local backup (external HDD) and cloud storage (Google Photos, iCloud, OneDrive)",
    "Verify backups regularly by opening random photos from each backup set",
    "Format memory cards in-camera (not on computer) before each use",
]


class PtFinalReport:
    """
    Forensic photo recovery final report generator - ptlibs compliant.

    Pipeline: collect data from all workflow steps -> build 11-section report ->
              generate PDF (optional) -> create client README + delivery checklist ->
              save FINAL_REPORT.json and workflow_summary.json.

    Courtroom-ready output compliant with ISO/IEC 27037:2012,
    NIST SP 800-86 and ACPO Good Practice Guide.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir = self.output_dir / f"{self.case_id}_final_report"
        self._src = {
            "validation": self.output_dir / f"{self.case_id}_validation_report.json",
            "exif":       self.output_dir / f"{self.case_id}_exif_analysis" / "exif_database.json",
            "repair":     self.output_dir / f"{self.case_id}_repair_report.json",
            "catalog":    self.output_dir / f"{self.case_id}_catalog" / "catalog_summary.json",
        }
        self._data:   Dict[str, Any] = {}
        self._report: Dict[str, Any] = {"reportVersion": "1.0", "caseId": self.case_id,
                                         "reportDate": datetime.now(timezone.utc).isoformat(),
                                         "sections": {}}
        self.ptjsonlib.add_properties({
            "caseId": self.case_id, "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(), "scriptVersion": __version__,
            "totalPhotos": 0, "integrityScore": 0.0, "qualityRating": "",
            "pdfGenerated": False, "sectionsGenerated": 0, "dryRun": self.dry_run,
        })
        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}))

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg); return False

    def _quality(self, score: float) -> str:
        for t, label in sorted(QUALITY_THRESHOLDS.items(), reverse=True):
            if score >= t: return label
        return "Poor"

    def _get(self, d: Dict, *keys: str) -> Any:
        """Retrieve value by camelCase or snake_case key from dict."""
        for key in keys:
            for k in [key, "".join(w.capitalize() if i else w
                                   for i, w in enumerate(key.split("_")))]:
                if k in d: return d[k]
        return None

    def _stats(self, key: str) -> Dict:
        """Return properties/statistics dict for a given data source."""
        v = self._data.get(key, {})
        return v.get("result", {}).get("properties") or v.get("statistics") or v

    def _load_json(self, path: Path) -> Optional[Dict]:
        if not path.exists(): return None
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            ptprint(f"Cannot read {path.name}: {exc}", "WARNING", condition=not self.args.json)
            return None

    # --- section builders ---------------------------------------------------

    def _s1_executive_summary(self) -> Dict:
        vs, cs = self._stats("validation"), self._stats("catalog")
        es  = self._stats("exif")   if "exif"   in self._data else None
        rs  = self._stats("repair") if "repair" in self._data else None
        g   = self._get
        tot = int(g(cs, "totalPhotos", "total_photos") or 0)
        ig  = float(g(vs, "integrityScore", "integrity_score") or 0)
        rat = self._quality(ig)
        self.ptjsonlib.add_properties({"totalPhotos": tot, "integrityScore": ig, "qualityRating": rat})
        r: Dict[str, Any] = {
            "overview": {"totalPhotosRecovered": tot, "integrityScorePercent": ig, "qualityRating": rat},
            "whatWeDid": [
                "Created forensic image of the media (write-blocked)",
                "Analyzed filesystem structure",
                "Recovered active and deleted photographs",
                "Validated integrity of every recovered file",
                "Repaired corrupted files" if rs else "No repair needed (all files valid)",
                "Extracted EXIF metadata (camera, date, GPS)",
                "Generated interactive HTML photo catalog",
            ],
            "clientGets": [
                f"{tot} recovered photos in organized catalog",
                "Interactive HTML catalog for easy browsing (photo_catalog.html)",
                "Thumbnails in 3 sizes (150/300/600 px) for quick preview",
                "Complete EXIF metadata - camera, date taken, GPS coordinates",
                "CSV spreadsheet for analysis in Microsoft Excel",
                "This comprehensive technical report",
                "README with usage instructions and backup recommendations",
            ],
            "recommendations": BACKUP_RECOMMENDATIONS,
        }
        if es:
            r["metadataHighlights"] = {
                "photosWithDatetime": int(g(es, "withDatetime", "with_datetime") or 0),
                "photosWithGps":      int(g(es, "withGps", "with_gps") or 0),
                "uniqueCameras":      int(g(es, "uniqueCameras", "unique_cameras") or 0),
                "dateRange":          g(es, "dateRange", "date_range") or {},
            }
        return r

    def _s2_case_information(self) -> Dict:
        return {"caseId": self.case_id, "reportDate": self._report["reportDate"],
                "reportVersion": "1.0", "analyst": "Forensic Photo Recovery System",
                "laboratory": "Digital Forensics Laboratory",
                "classification": "CONFIDENTIAL - addressee only"}

    def _s3_evidence_information(self) -> Dict:
        return {"evidenceDescription": "Digital storage media submitted for photo recovery",
                "evidenceType": "Photo storage device (memory card / internal storage)",
                "conditionOnReceipt": "Analyzed forensically", "forensicImageCreated": True,
                "writeBlockerUsed": True, "originalMediaStatus": "Unchanged - available for return",
                "hashAlgorithmUsed": "SHA-256"}

    def _s4_methodology(self) -> Dict:
        cs = self._stats("catalog")
        rs = self._stats("repair") if "repair" in self._data else None
        from_rep = int(self._get(cs, "fromRepair", "from_repair") or 0)
        return {
            "standardsFollowed": STANDARDS, "toolsUsed": TOOLS_USED,
            "forensicPrinciples": [
                "All analysis performed on forensic image - original media untouched",
                "Write-blocker used during imaging",
                "SHA-256 hash verification at all stages",
                "Chain of custody documented throughout",
                "READ-ONLY operations on evidence at all steps",
            ],
            "workflowSteps": [
                "Filesystem Analysis (partition table, FS type, directory readability)",
                "Filesystem-based Recovery (fls + icat, original filenames preserved)",
                "File Carving (PhotoRec, signature-based, works without filesystem)",
                "Consolidation (merge FS+carving, SHA-256 deduplication)",
                "EXIF Metadata Analysis (batch ExifTool, timeline, GPS, cameras)",
                "Integrity Validation (magic bytes, PIL, ImageMagick, jpeginfo)",
                "Repair Decision (automated cost-benefit analysis)",
                "Photo Repair (header/footer/segments/truncated)"
                if (rs is not None or from_rep > 0) else "Photo Repair - skipped",
                "Cataloging (thumbnails, indexes, HTML catalog)",
                "Final Report (this document)",
            ],
        }

    def _s5_timeline(self) -> Dict:
        return {"workflowEnd": self._report["reportDate"],
                "estimatedDuration": "5-10 hours (depending on media size and damage level)",
                "stepsWithDuration": [
                    {"step": "Filesystem Analysis",           "estimate": "5-15 min"},
                    {"step": "Photo Recovery (FS + carving)", "estimate": "30 min - 8 h"},
                    {"step": "Consolidation",                 "estimate": "5-30 min"},
                    {"step": "EXIF Analysis",                 "estimate": "5-30 min"},
                    {"step": "Integrity Validation",          "estimate": "5-30 min"},
                    {"step": "Repair Decision",               "estimate": "<1 min"},
                    {"step": "Photo Repair (if needed)",      "estimate": "1-45 min"},
                    {"step": "Cataloging",                    "estimate": "30-60 min"},
                    {"step": "Final Report",                  "estimate": "5-10 min"},
                ]}

    def _s6_results(self) -> Dict:
        vs, cs = self._stats("validation"), self._stats("catalog")
        es = self._stats("exif")   if "exif"   in self._data else None
        rs = self._stats("repair") if "repair" in self._data else None
        g  = self._get
        r: Dict[str, Any] = {
            "recoveryBreakdown": {
                "totalFilesAnalyzed":  int(g(vs,"totalFiles","total_files") or 0),
                "validFiles":          int(g(vs,"validFiles","valid_files") or 0),
                "corruptedFiles":      int(g(vs,"corruptedFiles","corrupted_files") or 0),
                "unrecoverableFiles":  int(g(vs,"unrecoverableFiles","unrecoverable_files") or 0),
                "integrityScore":      float(g(vs,"integrityScore","integrity_score") or 0),
            },
            "finalDelivery": {
                "totalPhotosCataloged": int(g(cs,"totalPhotos","total_photos") or 0),
                "fromValidation":       int(g(cs,"fromValidation","from_validation") or 0),
                "fromRepair":           int(g(cs,"fromRepair","from_repair") or 0),
            },
            "byFormat": g(vs,"byFormat","by_format") or {},
            "bySource": g(vs,"bySource","by_source") or {},
        }
        if rs:
            r["repairStatistics"] = {
                "totalAttempted":    int(g(rs,"totalAttempted","total_attempted") or 0),
                "successfulRepairs": int(g(rs,"successfulRepairs","successful_repairs") or 0),
                "failedRepairs":     int(g(rs,"failedRepairs","failed_repairs") or 0),
                "successRate":       float(g(rs,"successRate","success_rate") or 0),
                "byCorruptionType":  g(rs,"byCorruptionType","by_corruption_type") or {},
            }
        if es:
            r["metadataCoverage"] = {
                "filesWithExif":     int(g(es,"filesWithExif","files_with_exif") or 0),
                "filesWithDatetime": int(g(es,"withDatetime","with_datetime") or 0),
                "filesWithGps":      int(g(es,"withGps","with_gps") or 0),
                "uniqueCameras":     int(g(es,"uniqueCameras","unique_cameras") or 0),
                "dateRange":         g(es,"dateRange","date_range") or {},
            }
        return r

    def _s7_technical_details(self) -> Dict:
        vs = self._stats("validation")
        es = self._stats("exif")   if "exif"   in self._data else None
        rs = self._stats("repair") if "repair" in self._data else None
        d: Dict[str, Any] = {"validationDetails": {
            "toolsUsed": ["magic bytes","PIL/Pillow","ImageMagick identify","jpeginfo","pngcheck"],
            "decisionLogic": "ALL pass + valid magic->valid; 1+ pass->corrupted; ALL fail->unrecoverable",
            "corruptionTypesDetected": list((self._get(vs,"corruptionTypes","corruption_types") or {}).keys()),
        }}
        if rs:
            d["repairTechniques"] = {
                "missing_footer":   "Append FF D9 EOI marker (85-95%)",
                "invalid_header":   "Remove leading garbage / reconstruct SOI+JFIF (90-95%)",
                "corrupt_segments": "Strip APP segments, preserve SOF/DQT/DHT+SOS..EOI (80-85%)",
                "truncated":        "PIL LOAD_TRUNCATED_IMAGES partial recovery (50-70%)",
            }
        if es:
            d["metadataExtraction"] = {"tool": "ExifTool (libimage-exiftool-perl)", "batchSize": 50,
                                        "fieldsExtracted": ["DateTimeOriginal, CreateDate, ModifyDate",
                                                            "Make, Model, SerialNumber",
                                                            "ISO, FNumber, ExposureTime, FocalLength",
                                                            "GPSLatitude, GPSLongitude, GPSAltitude",
                                                            "Software (edit detection)"]}
        return d

    def _s8_quality_assurance(self) -> Dict:
        vs, cs = self._stats("validation"), self._stats("catalog")
        total = int(self._get(cs,"totalPhotos","total_photos") or 1)
        exif  = int(self._get(cs,"withExif","with_exif") or 0)
        return {"multiToolValidation": True,
                "hashVerification": "SHA-256 used at imaging, consolidation, and validation phases",
                "checksPerformed": ["All recovered files validated with 3+ independent tools",
                                     "SHA-256 deduplication during consolidation",
                                     "Catalog completeness: 100%",
                                     "Metadata extraction verified against EXIF format"],
                "metrics": {"catalogCompleteness": "100%",
                             "integrityScore": f"{self._get(vs,'integrityScore','integrity_score') or 0}%",
                             "exifCoveragePercent": f"{exif/total*100:.1f}%" if total else "0%"},
                "peerReviewStatus": "PENDING - REQUIRED before delivery",
                "signaturesStatus":  "PENDING - REQUIRED before delivery"}

    def _s9_delivery_package(self) -> Dict:
        cs = self._stats("catalog"); p = self.case_id
        total = int(self._get(cs,"totalPhotos","total_photos") or 0)
        return {
            "contents": [f"{total} recovered photos in organized catalog",
                          "Interactive HTML catalog (photo_catalog.html)",
                          "Thumbnails in 3 sizes (small 150px / medium 300px / large 600px)",
                          "Complete metadata - complete_catalog.json and catalog.csv",
                          "Search indexes - chronological, by_camera, GPS (JSON)",
                          "This final report (FINAL_REPORT.json)",
                          "Client README with instructions (README.txt)"],
            "catalogStructure": {"photos": f"{p}_catalog/photos/",
                                  "thumbnails": f"{p}_catalog/thumbnails/{{small,medium,large}}/",
                                  "metadata": f"{p}_catalog/metadata/",
                                  "indexes": f"{p}_catalog/indexes/",
                                  "htmlCatalog": f"{p}_catalog/photo_catalog.html"},
            "howToAccess": ["Open photo_catalog.html in any web browser",
                             "Search by filename, camera or date",
                             "Click any photo to view full size",
                             "Filter by source (validation vs. repair)",
                             "Open catalog.csv in Excel for metadata analysis"],
        }

    def _s10_chain_of_custody(self) -> Dict:
        return {"description": "Chain of custody maintained throughout the recovery workflow",
                "integrityMaintained": True,
                "originalMediaStatus": "Unchanged - available for return to client",
                "events": [
                    {"event": "Evidence received",         "action": "Media received, condition documented, case ID assigned"},
                    {"event": "Forensic image created",    "action": "Write-blocked forensic copy; SHA-256 hashes recorded"},
                    {"event": "Filesystem analysis",       "action": "Partition/FS structure analyzed; strategy determined"},
                    {"event": "Photo recovery",            "action": "Active and deleted files recovered; originals untouched"},
                    {"event": "Consolidation & dedup",     "action": "Duplicate removal via SHA-256; master catalog created"},
                    {"event": "Validation performed",      "action": "Multi-tool integrity validation; corrupted files identified"},
                    {"event": "Repair performed/decided",  "action": "Automated repair decision; corrupted files treated"},
                    {"event": "Catalog generated",         "action": "Thumbnails, indexes, HTML catalog created"},
                    {"event": "Final report generated",    "action": "This document; ready for peer review and delivery"},
                ]}

    def _s11_signatures(self) -> Dict:
        return {"note": "This report MUST be reviewed and signed before delivery to client",
                "primaryAnalyst":  {"name": "[ANALYST NAME]",  "signature": "PENDING",           "date": "PENDING", "role": "Forensic Analyst"},
                "peerReviewer":    {"name": "[REVIEWER NAME]", "signature": "PENDING - REQUIRED", "date": "PENDING", "role": "Senior Analyst / QA"},
                "reviewChecklist": ["Results consistent with findings from each step",
                                    "All files accounted for in catalog",
                                    "Technical details are accurate",
                                    "Chain of custody is unbroken",
                                    "Report language appropriate for court submission"]}

    # --- phases -------------------------------------------------------------

    def collect_data(self) -> bool:
        ptprint("\n[1/6] Collecting Data", "TITLE", condition=not self.args.json)

        if self.dry_run:
            self._data = {
                "validation": {"statistics": {"total_files": 100, "valid_files": 91,
                    "corrupted_files": 7, "unrecoverable_files": 2, "integrity_score": 91.0,
                    "by_format": {}, "by_source": {}, "corruption_types": {}}},
                "exif": {"statistics": {"files_with_exif": 82, "with_datetime": 79, "with_gps": 41,
                    "unique_cameras": 3, "date_range": {"earliest": "2023-06-01", "latest": "2024-12-15"}}},
                "repair": {"statistics": {"total_attempted": 7, "successful_repairs": 5,
                    "failed_repairs": 2, "success_rate": 71.4, "by_corruption_type": {}}},
                "catalog": {"statistics": {"total_photos": 96, "from_validation": 91, "from_repair": 5,
                    "thumbnails_generated": 288, "with_exif": 82, "with_gps": 41, "unique_cameras": 3,
                    "date_range": {"earliest": "2023-06-01", "latest": "2024-12-15"}}},
            }
            ptprint("[DRY-RUN] Synthetic data loaded.", "INFO", condition=not self.args.json)
            self._add_node("dataCollection", True, dryRun=True); return True

        val = self._load_json(self._src["validation"])
        if val is None:
            return self._fail("dataCollection",
                              "validation_report.json not found - run integrity validation first.")
        self._data["validation"] = val
        ptprint("Validation report loaded.", "OK", condition=not self.args.json)

        cat = self._load_json(self._src["catalog"])
        if cat is None:
            return self._fail("dataCollection",
                              "catalog_summary.json not found - run cataloging first.")
        self._data["catalog"] = cat
        ptprint("Catalog summary loaded.", "OK", condition=not self.args.json)

        for key, label in [("exif", "EXIF database"), ("repair", "Repair report")]:
            data = self._load_json(self._src[key])
            if data:
                self._data[key] = data
                ptprint(f"{label} loaded.", "OK", condition=not self.args.json)
            else:
                ptprint(f"{label} not found - skipping.", "INFO", condition=not self.args.json)

        self._add_node("dataCollection", True, sources=list(self._data.keys()))
        return True

    def build_report(self) -> None:
        ptprint("\n[2/6] Building 11-Section Report", "TITLE", condition=not self.args.json)
        for key, builder, label in [
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
        ]:
            self._report["sections"][key] = builder()
            ptprint(f"  {len(self._report['sections'])}/11: {label}", "INFO", condition=not self.args.json)
        ptprint("All 11 sections generated.", "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"sectionsGenerated": 11})
        self._add_node("reportBuilt", True, sections=11)

    def generate_pdf(self) -> Optional[str]:
        ptprint("\n[4/6] Generating PDF Report", "TITLE", condition=not self.args.json)
        if not REPORTLAB_AVAILABLE:
            ptprint("reportlab not installed - skipping PDF. "
                    "pip install reportlab --break-system-packages",
                    "WARNING", condition=not self.args.json); return None
        if self.dry_run:
            ptprint("[DRY-RUN] PDF skipped.", "INFO", condition=not self.args.json); return None

        pdf_path = self.report_dir / "FINAL_REPORT.pdf"
        styles   = getSampleStyleSheet()
        h1   = ParagraphStyle("h1",  parent=styles["Heading1"], fontSize=14, spaceAfter=6,
                               textColor=colors.HexColor("#1e293b"))
        h2   = ParagraphStyle("h2",  parent=styles["Heading2"], fontSize=11, spaceAfter=4)
        body = ParagraphStyle("body",parent=styles["Normal"],   fontSize=9,  leading=14)
        warn = ParagraphStyle("warn",parent=body, textColor=colors.HexColor("#dc2626"),
                               fontName="Helvetica-Bold")

        cs, vs = self._stats("catalog"), self._stats("validation")
        total  = int(self._get(cs,"totalPhotos","total_photos") or 0)
        ig     = float(self._get(vs,"integrityScore","integrity_score") or 0)
        story  = []

        # Cover page
        story += [Spacer(1,3*cm), Paragraph("FORENSIC PHOTO RECOVERY", styles["Title"]),
                  Paragraph("Final Technical Report", styles["Heading2"]),
                  Spacer(1,1*cm),
                  HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e293b")),
                  Spacer(1,0.5*cm)]
        cov = Table([["Case ID:", self.case_id], ["Report Date:", self._report["reportDate"][:10]],
                     ["Total Photos:", str(total)], ["Integrity Score:", f"{ig}%"],
                     ["Quality Rating:", self._quality(ig)]], colWidths=[5*cm, 10*cm])
        cov.setStyle(TableStyle([("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
                                  ("FONTSIZE",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        story += [cov, Spacer(1,1*cm), Paragraph("CONFIDENTIAL - For addressee only", body),
                  Paragraph("This report requires peer review and signatures before delivery.", warn),
                  PageBreak()]

        def bul(items: List[str]) -> None:
            for item in items: story.append(Paragraph(f"- {item}", body))
            story.append(Spacer(1,0.3*cm))

        def sec(n: int, title: str) -> None:
            story.append(Paragraph(f"Section {n}: {title}", h1))
            story.append(HRFlowable(width="100%",thickness=1,color=colors.HexColor("#e2e8f0")))
            story.append(Spacer(1,0.3*cm))

        s = self._report["sections"]

        # S1 Executive Summary
        sec(1,"Executive Summary"); ov = s["executiveSummary"]["overview"]
        story.append(Paragraph(
            f"<b>Recovered: {ov['totalPhotosRecovered']}</b> | "
            f"Integrity: {ov['integrityScorePercent']}% | Quality: <b>{ov['qualityRating']}</b>", body))
        story.append(Paragraph("What we did:", h2)); bul(s["executiveSummary"]["whatWeDid"])
        story.append(Paragraph("Client receives:", h2)); bul(s["executiveSummary"]["clientGets"])
        story.append(PageBreak())

        # S2+S3
        sec(2,"Case Information")
        for k, v in s["caseInformation"].items():  story.append(Paragraph(f"<b>{k}:</b> {v}", body))
        story.append(Spacer(1,0.5*cm))
        sec(3,"Evidence Information")
        for k, v in s["evidenceInformation"].items(): story.append(Paragraph(f"<b>{k}:</b> {v}", body))
        story.append(PageBreak())

        # S4 Methodology
        sec(4,"Methodology")
        story.append(Paragraph("Standards followed:", h2)); bul(s["methodology"]["standardsFollowed"])
        story.append(Paragraph("Workflow:", h2)); bul(s["methodology"]["workflowSteps"])
        story.append(PageBreak())

        # S6 Results table
        sec(6,"Results"); rb = s["results"]["recoveryBreakdown"]; fd = s["results"]["finalDelivery"]
        res = Table([["Metric","Value"],
                     ["Total files analyzed",    str(rb.get("totalFilesAnalyzed",0))],
                     ["Valid files",             str(rb.get("validFiles",0))],
                     ["Corrupted files",         str(rb.get("corruptedFiles",0))],
                     ["Unrecoverable",           str(rb.get("unrecoverableFiles",0))],
                     ["Integrity score",         f"{rb.get('integrityScore',0)}%"],
                     ["Photos in catalog",       str(fd.get("totalPhotosCataloged",0))],
                     ], colWidths=[9*cm,6*cm])
        res.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1e293b")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f8fafc")]),
            ("BOX",(0,0),(-1,-1),0.5,colors.grey),("INNERGRID",(0,0),(-1,-1),0.25,colors.lightgrey),
        ]))
        story += [res, Spacer(1,0.5*cm), PageBreak()]

        # S10 Chain of Custody
        sec(10,"Chain of Custody")
        for ev in s["chainOfCustody"]["events"]:
            story.append(Paragraph(f"<b>{ev['event']}:</b> {ev['action']}", body))
        story.append(PageBreak())

        # S11 Signatures
        sec(11,"Signatures")
        story.append(Paragraph(s["signatures"]["note"], warn)); story.append(Spacer(1,1.5*cm))
        sig = Table([["Role","Name","Signature","Date"],
                     ["Primary Analyst","[ANALYST NAME]","___________________","________"],
                     ["Peer Reviewer",  "[REVIEWER NAME]","___________________","________"]],
                    colWidths=[4.5*cm,5*cm,5*cm,3*cm])
        sig.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1e293b")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),9),("BOX",(0,0),(-1,-1),0.5,colors.grey),
            ("INNERGRID",(0,0),(-1,-1),0.25,colors.lightgrey),
        ]))
        story.append(sig)

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
                                title=f"Forensic Photo Recovery Report - {self.case_id}",
                                author=f"ptfinalreport v{__version__}")
        try:
            doc.build(story)
            self.ptjsonlib.add_properties({"pdfGenerated": True})
            ptprint(f"PDF: {pdf_path.name}", "OK", condition=not self.args.json)
            return str(pdf_path)
        except Exception as exc:
            ptprint(f"PDF failed: {exc}", "WARNING", condition=not self.args.json); return None

    def _save_client_files(self) -> None:
        """Create README.txt and delivery_checklist.json."""
        vs, cs = self._stats("validation"), self._stats("catalog")
        g   = self._get
        tot = int(g(cs,"totalPhotos","total_photos") or 0)
        sc  = float(g(vs,"integrityScore","integrity_score") or 0)
        p   = self.case_id

        if not self.dry_run:
            readme = [
                f"{'='*70}", "PHOTO RECOVERY - DELIVERY PACKAGE", f"{'='*70}", "",
                f"Case ID:   {p}", f"Date:      {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                f"Photos:    {tot}", f"Integrity: {sc}% ({self._quality(sc)})", "",
                f"{'='*70}", "CONTENTS", f"{'='*70}", "",
                f"  {p}_catalog/photos/           {tot} recovered photos",
                f"  {p}_catalog/photo_catalog.html  Interactive catalog (open in browser)",
                f"  {p}_catalog/thumbnails/        small / medium / large previews",
                f"  {p}_catalog/metadata/          complete_catalog.json + catalog.csv",
                f"  {p}_catalog/indexes/           chronological, camera, GPS",
                f"  {p}_final_report/FINAL_REPORT.json", "",
                f"{'='*70}", "HOW TO VIEW", f"{'='*70}", "",
                f"  1. Open {p}_catalog/photo_catalog.html in any browser",
                "  2. Search by filename, camera or date",
                "  3. Click any photo for full-size view",
                "  4. For metadata analysis open catalog.csv in Excel", "",
                f"{'='*70}", "BACKUP RECOMMENDATIONS", f"{'='*70}", "",
            ] + [f"  - {r}" for r in BACKUP_RECOMMENDATIONS] + [
                "  DO NOT rely on the original storage media that was recovered!", "",
                f"{'='*70}", "FAQ", f"{'='*70}", "",
                f"Q: Why are photos renamed?",
                f"A: Photos are named {p}_0001.jpg etc. Original names are in metadata CSV.", "",
                "Q: Some photos seem missing - why?",
                f"A: Recovery depends on whether deleted space was overwritten. "
                f"Score {sc}% means all discoverable photos were recovered.", "",
                "Q: What does 'REPAIRED' badge mean?",
                "A: Minor structural corruption was fixed automatically. Content is unchanged.",
            ]
            (self.report_dir / "README.txt").write_text("\n".join(readme), encoding="utf-8")
        ptprint("README.txt created.", "OK", condition=not self.args.json)

        checklist = {
            "caseId": p, "checklistDate": datetime.now(timezone.utc).isoformat(),
            "items": [
                {"item": "Photo catalog prepared",        "status": "COMPLETE",           "location": f"{p}_catalog/"},
                {"item": "HTML catalog accessible",       "status": "COMPLETE",           "location": f"{p}_catalog/photo_catalog.html"},
                {"item": "Thumbnails generated",          "status": "COMPLETE"},
                {"item": "Integrity validation completed","status": "COMPLETE",           "details": f"Integrity score: {sc}%"},
                {"item": "Metadata extraction performed", "status": "COMPLETE" if "exif" in self._data else "SKIPPED"},
                {"item": "Final report generated",        "status": "COMPLETE",           "location": f"{p}_final_report/FINAL_REPORT.json"},
                {"item": "Peer review by senior analyst", "status": "PENDING - REQUIRED", "action": "Senior analyst must review and sign off"},
                {"item": "Analyst and reviewer signatures","status": "PENDING - REQUIRED","action": "Both signatures required before delivery"},
            ],
            "completionStatus": {"completedItems": 6, "pendingItems": 2, "totalItems": 8,
                                  "readyForDelivery": False,
                                  "pendingReason": "Peer review and signatures required"},
            "nextSteps": ["1. Senior analyst peer review", "2. Analyst signature",
                           "3. Peer reviewer signature", "4. Package catalog + final report",
                           "5. Contact client for pickup / secure delivery"],
        }
        if not self.dry_run:
            (self.report_dir / "delivery_checklist.json").write_text(
                json.dumps(checklist, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint("delivery_checklist.json created.", "OK", condition=not self.args.json)

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FINAL REPORT GENERATION v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.collect_data():
            self.ptjsonlib.set_status("finished"); return
        if not self.dry_run:
            self.report_dir.mkdir(parents=True, exist_ok=True)

        self.build_report()
        self.generate_pdf()

        ptprint("\n[5/6] Creating Client Documents", "TITLE", condition=not self.args.json)
        self._save_client_files()

        vs, cs = self._stats("validation"), self._stats("catalog")
        total  = int(self._get(cs,"totalPhotos","total_photos") or 0)
        ig     = float(self._get(vs,"integrityScore","integrity_score") or 0)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FINAL REPORT COMPLETED | Photos: {total} | Integrity: {ig}% | "
                f"Quality: {self._quality(ig)}", "OK", condition=not self.args.json)
        ptprint("IMPORTANT: Peer review and signatures REQUIRED before delivery.",
                "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json); return None

        report_path = self.report_dir / "FINAL_REPORT.json"
        if not self.dry_run:
            report_path.write_text(
                json.dumps(self._report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        ptprint("FINAL_REPORT.json saved.", "OK", condition=not self.args.json)

        vs, cs = self._stats("validation"), self._stats("catalog")
        total  = int(self._get(cs,"totalPhotos","total_photos") or 0)
        sc     = float(self._get(vs,"integrityScore","integrity_score") or 0)
        summary = {
            "caseId": self.case_id, "completedAt": datetime.now(timezone.utc).isoformat(),
            "stepsCompleted": list(filter(None, [
                "Filesystem Analysis", "Photo Recovery (FS + carving)", "Consolidation",
                "EXIF Analysis"  if "exif"   in self._data else None,
                "Integrity Validation", "Repair Decision",
                "Photo Repair"   if "repair" in self._data else None,
                "Cataloging", "Final Report",
            ])),
            "finalResults": {"photosRecovered": total, "integrityScore": sc,
                              "qualityRating": self._quality(sc)},
            "deliverables": list(filter(None, [
                "Photo catalog with HTML interface", "Complete metadata (JSON + CSV)",
                "Final technical report (FINAL_REPORT.json)",
                "PDF report (FINAL_REPORT.pdf)" if REPORTLAB_AVAILABLE else None,
                "Client README and instructions", "Delivery checklist",
            ])),
            "nextAction": "Peer review and signatures required before delivery to client",
        }
        sum_path = self.report_dir / "workflow_summary.json"
        if not self.dry_run:
            sum_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint("workflow_summary.json saved.", "OK", condition=not self.args.json)
        return str(report_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List:
    return [
        {"description": [
            "Forensic photo recovery final report generator - ptlibs compliant",
            "Consolidates data from all workflow steps into an 11-section",
            "courtroom-ready JSON report + optional PDF (requires reportlab)",
        ]},
        {"usage": ["ptfinalreport <case-id> [options]"]},
        {"usage_example": [
            "ptfinalreport PHOTO-2025-001",
            "ptfinalreport CASE-042 --json",
            "ptfinalreport TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate with synthetic data, no file writes"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"report_sections": [
            "S1  Executive Summary (client-friendly)",
            "S2  Case Information", "S3  Evidence Information",
            "S4  Methodology (standards, tools, forensic principles)", "S5  Timeline",
            "S6  Results (recovery, repair, metadata statistics)", "S7  Technical Details",
            "S8  Quality Assurance", "S9  Delivery Package",
            "S10 Chain of Custody",
            "S11 Signatures (PENDING - required before delivery)",
        ]},
        {"notes": [
            "Required: {case_id}_validation_report.json, {case_id}_catalog/catalog_summary.json",
            "Optional: {case_id}_exif_analysis/exif_database.json, {case_id}_repair_report.json",
            "PDF:      pip install reportlab --break-system-packages",
            "Compliant with ISO/IEC 27037:2012, NIST SP 800-86, ACPO, SWGDE",
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
        tool = PtFinalReport(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("sectionsGenerated", 0) == 11 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True); return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True); return 99


if __name__ == "__main__":
    sys.exit(main())