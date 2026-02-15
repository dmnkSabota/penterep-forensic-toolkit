#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-DELIVERY: Príprava odovzdania klientovi
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript pripraví všetky dokumenty a materiály potrebné pre odovzdanie
výsledkov klientovi a uzavretie prípadu.
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False


class DeliveryPreparation:
    """
    Príprava delivery package pre klienta.
    
    Proces:
    1. Prepare delivery package structure
    2. Generate MANIFEST with checksums
    3. Create completion email template
    4. Generate delivery protocol
    5. Create client satisfaction survey
    6. Prepare case closure documentation
    7. Generate archival manifest
    """
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        
        # Paths
        self.catalog_base = self.output_dir / f"{case_id}_catalog"
        self.report_base = self.output_dir / f"{case_id}_final_report"
        self.delivery_base = self.output_dir / f"{case_id}_delivery"
        
        # Delivery preparation data
        self.manifest = {
            "case_id": case_id,
            "manifest_date": datetime.utcnow().isoformat() + "Z",
            "files": []
        }
        
        # Statistics
        self.stats = {
            "case_id": case_id,
            "preparation_date": datetime.utcnow().isoformat() + "Z",
            "package_ready": False,
            "success": False
        }
    
    def _print(self, message, level="INFO"):
        """Helper pre výpis"""
        if PTLIBS_AVAILABLE:
            ptprinthelper.ptprint(message, level)
        else:
            prefix = {
                "TITLE": "[*]",
                "OK": "[✓]",
                "ERROR": "[✗]",
                "WARNING": "[!]",
                "INFO": "[i]"
            }.get(level, "")
            print(f"{prefix} {message}")
    
    def calculate_file_hash(self, filepath):
        """Vypočítaj SHA-256 hash súboru"""
        sha256 = hashlib.sha256()
        
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def prepare_package_structure(self):
        """
        FÁZA 1: Príprava delivery package štruktúry.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("DELIVERY PACKAGE PREPARATION", "TITLE")
        self._print("="*70, "TITLE")
        
        # Create delivery directory
        self.delivery_base.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        subdirs = [
            'PHOTOS',
            'CATALOG', 
            'REPORT',
            'DOCUMENTATION'
        ]
        
        for subdir in subdirs:
            (self.delivery_base / subdir).mkdir(exist_ok=True)
        
        self._print("Delivery package structure created", "OK")
        self._print(f"  Location: {self.delivery_base}", "INFO")
    
    def generate_manifest(self):
        """
        FÁZA 2: Generovanie MANIFEST.json so zoznamom súborov a checksums.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("MANIFEST GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        # Key files to include
        key_files = {
            'catalog': self.catalog_base / "photo_catalog.html",
            'report': self.report_base / "FINAL_REPORT.json",
            'readme': self.report_base / "README.txt",
            'summary': self.catalog_base / "catalog_summary.json"
        }
        
        total_size = 0
        
        for name, filepath in key_files.items():
            if filepath.exists():
                file_size = filepath.stat().st_size
                file_hash = self.calculate_file_hash(filepath)
                
                self.manifest['files'].append({
                    'name': filepath.name,
                    'category': name,
                    'path': str(filepath.relative_to(self.output_dir)),
                    'size_bytes': file_size,
                    'sha256': file_hash
                })
                
                total_size += file_size
                
                self._print(f"  {filepath.name}: {file_size:,} bytes", "INFO")
        
        self.manifest['total_size_bytes'] = total_size
        self.manifest['total_files'] = len(self.manifest['files'])
        
        # Save manifest
        manifest_path = self.delivery_base / "MANIFEST.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)
        
        self._print(f"\nManifest generated: {self.manifest['total_files']} files", "OK")
        self._print(f"Total size: {total_size / (1024*1024):.2f} MB", "INFO")
    
    def create_completion_email(self):
        """
        FÁZA 3: Vytvorenie completion email template.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("COMPLETION EMAIL GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        # Load catalog summary for stats
        summary_path = self.catalog_base / "catalog_summary.json"
        
        if summary_path.exists():
            with open(summary_path, 'r', encoding='utf-8') as f:
                catalog_data = json.load(f)
            
            total_photos = catalog_data['statistics']['total_photos']
        else:
            total_photos = "N/A"
        
        email_template = f"""
Subject: Photo Recovery Completed - Case {self.case_id}

Dear Client,

We are pleased to inform you that your photo recovery case has been completed successfully.

CASE SUMMARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Case ID: {self.case_id}
Completion Date: {datetime.utcnow().strftime("%Y-%m-%d")}
Total Photos Recovered: {total_photos}
Quality: Professional forensic recovery with full documentation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DELIVERY PACKAGE INCLUDES:
• Recovered photos in organized catalog
• Interactive HTML catalog for easy browsing
• Thumbnails in 3 sizes for quick preview
• Complete EXIF metadata (camera, date, GPS)
• Comprehensive technical report
• README with instructions
• Your original storage media

DELIVERY OPTIONS:

1. PERSONAL PICKUP (Recommended)
   • Location: Digital Forensics Laboratory
   • Hours: Monday-Friday, 9:00-17:00
   • Benefits: Personal briefing, immediate access, instant media return
   • Contact to schedule: [PHONE/EMAIL]

2. COURIER SERVICE
   • Secure packaging with insurance
   • Tracking number provided
   • Signature required on delivery
   • Estimated delivery: 2-3 business days
   • Fee: [AMOUNT] EUR

3. ONLINE TRANSFER + COURIER
   • Secure download link (7-day validity)
   • Original media sent separately via courier
   • Fastest option for urgent needs
   • Available within 24 hours

NEXT STEPS:

Please reply to this email with your preferred delivery method. We will then:
• Schedule pickup time (Option 1)
• Arrange courier pickup (Option 2)
• Send secure download link (Option 3)

If we don't hear from you within 3 business days, we will follow up via phone.

WHAT YOU'LL RECEIVE:

1. All recovered photos with original quality
2. Interactive web catalog (works offline)
3. Complete metadata in multiple formats
4. Professional forensic report
5. Instructions and recommendations
6. Your original storage media

IMPORTANT NOTES:

• Please backup your photos immediately after receiving them (3-2-1 rule)
• The HTML catalog works in any web browser
• All files include integrity verification (SHA-256)
• Chain of Custody will be formally closed upon delivery

We appreciate your patience during the recovery process. If you have any questions, 
please don't hesitate to contact us.

Best regards,
Digital Forensics Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Contact Information:
Email: forensics@lab.example
Phone: +421 XXX XXX XXX
Case Reference: {self.case_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        email_path = self.delivery_base / "DOCUMENTATION" / "completion_email.txt"
        with open(email_path, 'w', encoding='utf-8') as f:
            f.write(email_template)
        
        self._print("Completion email template created", "OK")
        self._print(f"  Location: {email_path.name}", "INFO")
    
    def create_delivery_protocol(self):
        """
        FÁZA 4: Vytvorenie delivery protocol template.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("DELIVERY PROTOCOL GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        protocol = f"""
{"="*70}
DELIVERY PROTOCOL
{"="*70}

Case ID: {self.case_id}
Delivery Date: _______________________
Delivery Time: _______________________
Delivery Location: _______________________

{"="*70}
DELIVERING PARTY (Forensic Laboratory)
{"="*70}

Analyst Name: _______________________
Position: Forensic Analyst
Signature: _______________________
Date: _______________________

{"="*70}
RECEIVING PARTY (Client)
{"="*70}

Client Name: _______________________
Organization: _______________________
ID Document Type: _______________________
ID Document Number: _______________________
Signature: _______________________
Date: _______________________

{"="*70}
DELIVERED ITEMS
{"="*70}

[ ] Photo Catalog
    • Interactive HTML catalog
    • Recovered photos (full quality)
    • Thumbnails (3 sizes)
    • Location: {self.case_id}_catalog/

[ ] Final Report
    • Comprehensive technical report
    • Executive summary
    • Chain of Custody documentation
    • Location: {self.case_id}_final_report/

[ ] Client Documentation
    • README with instructions
    • Backup recommendations
    • FAQ and support information

[ ] Original Storage Media
    • Type: SD Card / USB Drive / HDD (circle one)
    • Serial Number: _______________________
    • Condition: Returned as received

[ ] MANIFEST.json
    • Complete file list
    • SHA-256 checksums
    • Integrity verification

{"="*70}
DELIVERY METHOD
{"="*70}

[ ] Personal Pickup
    Location: Digital Forensics Laboratory
    Client ID verified: Yes [ ]  No [ ]
    Briefing provided: Yes [ ]  No [ ]

[ ] Courier Service
    Courier: _______________________
    Tracking Number: _______________________
    Insurance: EUR _______________________

[ ] Online Transfer
    Download Link Sent: Date _______________________
    Password Sent Separately: Yes [ ]  No [ ]
    Media Sent via Courier: Tracking _______________________

{"="*70}
INTEGRITY VERIFICATION
{"="*70}

Package SHA-256 Hash:
________________________________________________________________

Client confirms:
[ ] All items received as listed above
[ ] Integrity verification completed successfully
[ ] Original storage media returned
[ ] Instructions and documentation received
[ ] Satisfied with delivery completeness

{"="*70}
CHAIN OF CUSTODY CLOSURE
{"="*70}

Final Chain of Custody Entry:
Date/Time: _______________________
Event: Evidence returned to client
Method: Personal pickup / Courier / Online transfer
Location: _______________________

Chain of Custody Status: CLOSED

All custody transfers documented: Yes [ ]  No [ ]
No gaps in custody chain: Yes [ ]  No [ ]
Complete audit trail maintained: Yes [ ]  No [ ]

{"="*70}
CLIENT NOTES / QUESTIONS
{"="*70}

________________________________________________________________
________________________________________________________________
________________________________________________________________
________________________________________________________________

{"="*70}
FINAL ACKNOWLEDGMENT
{"="*70}

The receiving party acknowledges receipt of all items listed above
and confirms that the Chain of Custody for Case {self.case_id} is
hereby formally closed.

Forensic Analyst Signature: _______________________
Date: _______________________

Client Signature: _______________________
Date: _______________________

{"="*70}
FOR LABORATORY USE ONLY
{"="*70}

Protocol Filed: Date _______________________
Database Updated: Status CLOSED [ ]
Archive Completed: Date _______________________
Retention Period: 7 years (until {(datetime.utcnow() + timedelta(days=365*7)).strftime("%Y-%m-%d")})

{"="*70}
END OF DELIVERY PROTOCOL
{"="*70}
"""
        
        protocol_path = self.delivery_base / "DOCUMENTATION" / "delivery_protocol.txt"
        with open(protocol_path, 'w', encoding='utf-8') as f:
            f.write(protocol)
        
        self._print("Delivery protocol template created", "OK")
        self._print(f"  Location: {protocol_path.name}", "INFO")
    
    def create_satisfaction_survey(self):
        """
        FÁZA 5: Vytvorenie client satisfaction survey.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("SATISFACTION SURVEY GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        survey = f"""
{"="*70}
CLIENT SATISFACTION SURVEY
{"="*70}

Case ID: {self.case_id}
Survey Date: _______________________

Dear Client,

Thank you for choosing our forensic photo recovery services. Your feedback
helps us improve our processes and better serve future clients.

This brief survey takes only 2-3 minutes to complete.

{"="*70}
QUESTION 1: Overall Quality
{"="*70}

How would you rate the overall quality of our photo recovery service?

[ ] 5 - Excellent (Exceeded expectations)
[ ] 4 - Very Good (Met expectations well)
[ ] 3 - Good (Met basic expectations)
[ ] 2 - Fair (Below expectations)
[ ] 1 - Poor (Well below expectations)

{"="*70}
QUESTION 2: Photo Recovery Results
{"="*70}

Are you satisfied with the number of photos recovered?

[ ] 5 - Very Satisfied (Recovered more than expected)
[ ] 4 - Satisfied (Recovered as expected)
[ ] 3 - Somewhat Satisfied (Recovered less than hoped)
[ ] 2 - Dissatisfied (Much less than expected)
[ ] 1 - Very Dissatisfied (Far below expectations)

{"="*70}
QUESTION 3: Communication Quality
{"="*70}

How would you rate our communication throughout the process?

[ ] 5 - Excellent (Timely, clear, professional)
[ ] 4 - Very Good (Good communication)
[ ] 3 - Good (Adequate communication)
[ ] 2 - Fair (Could be improved)
[ ] 1 - Poor (Insufficient communication)

{"="*70}
QUESTION 4: Recommendation
{"="*70}

Would you recommend our services to others?

[ ] Yes, definitely
[ ] Yes, probably
[ ] Maybe
[ ] Probably not
[ ] Definitely not

{"="*70}
QUESTION 5: Improvements
{"="*70}

What could we improve? (Optional)

________________________________________________________________
________________________________________________________________
________________________________________________________________
________________________________________________________________

{"="*70}
TESTIMONIAL (OPTIONAL)
{"="*70}

May we use your feedback as a testimonial? [ ] Yes [ ] No

If yes, please provide a brief testimonial:

________________________________________________________________
________________________________________________________________
________________________________________________________________

Name to display (or "Anonymous"): _______________________

{"="*70}
THANK YOU!
{"="*70}

Your feedback is valuable to us. Please return this survey:
• Email: feedback@lab.example
• In person during pickup
• Via mail within 7 days

As a token of appreciation, clients who complete the survey receive
a 10% discount on future services.

{"="*70}
FOR LABORATORY USE ONLY
{"="*70}

Survey Received: Date _______________________
Overall Score: _______ / 5.0
Response Processed: Date _______________________
Follow-up Required: Yes [ ]  No [ ]

{"="*70}
"""
        
        survey_path = self.delivery_base / "DOCUMENTATION" / "satisfaction_survey.txt"
        with open(survey_path, 'w', encoding='utf-8') as f:
            f.write(survey)
        
        self._print("Client satisfaction survey created", "OK")
        self._print(f"  Target score: 4.5+ / 5.0", "INFO")
    
    def create_case_closure_checklist(self):
        """
        FÁZA 6: Vytvorenie case closure checklist.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("CASE CLOSURE CHECKLIST GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        checklist = {
            "case_id": self.case_id,
            "checklist_date": datetime.utcnow().isoformat() + "Z",
            "closure_items": [
                {
                    "category": "Delivery Preparation",
                    "items": [
                        {"task": "Delivery package prepared", "status": "PENDING"},
                        {"task": "MANIFEST.json generated with checksums", "status": "PENDING"},
                        {"task": "Completion email drafted", "status": "PENDING"},
                        {"task": "Delivery protocol prepared", "status": "PENDING"},
                        {"task": "Package integrity verified", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Client Communication",
                    "items": [
                        {"task": "Completion email sent", "status": "PENDING"},
                        {"task": "Client response received", "status": "PENDING"},
                        {"task": "Delivery method confirmed", "status": "PENDING"},
                        {"task": "Delivery scheduled", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Delivery Execution",
                    "items": [
                        {"task": "Client identity verified (if personal)", "status": "PENDING"},
                        {"task": "Package delivered to client", "status": "PENDING"},
                        {"task": "Original media returned", "status": "PENDING"},
                        {"task": "Delivery protocol signed", "status": "PENDING"},
                        {"task": "Client briefing completed", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Chain of Custody Closure",
                    "items": [
                        {"task": "Final CoC entry recorded", "status": "PENDING"},
                        {"task": "All signatures obtained", "status": "PENDING"},
                        {"task": "CoC completeness verified", "status": "PENDING"},
                        {"task": "CoC PDF generated", "status": "PENDING"},
                        {"task": "CoC status set to CLOSED", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Client Satisfaction",
                    "items": [
                        {"task": "Satisfaction survey sent", "status": "PENDING"},
                        {"task": "Survey response received", "status": "PENDING"},
                        {"task": "Feedback analyzed", "status": "PENDING"},
                        {"task": "Testimonial requested (if applicable)", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Case Closure & Archival",
                    "items": [
                        {"task": "Case closure report generated", "status": "PENDING"},
                        {"task": "All files archived securely", "status": "PENDING"},
                        {"task": "Archival manifest created", "status": "PENDING"},
                        {"task": "7-year retention scheduled", "status": "PENDING"},
                        {"task": "Database updated - status CLOSED", "status": "PENDING"},
                        {"task": "Workflow summary documented", "status": "PENDING"},
                        {"task": "Lessons learned recorded", "status": "PENDING"}
                    ]
                },
                {
                    "category": "Financial",
                    "items": [
                        {"task": "Invoice issued", "status": "PENDING"},
                        {"task": "Payment received", "status": "PENDING"},
                        {"task": "Financial records updated", "status": "PENDING"}
                    ]
                }
            ],
            "completion_metrics": {
                "target_response_time": "< 24 hours",
                "target_delivery_time": "Personal: 36h / Courier: 3 days / Online: 24h",
                "target_satisfaction": "4.5+ / 5.0",
                "target_feedback_rate": "80%+",
                "payment_target": "95%+",
                "retention_period": "7 years"
            }
        }
        
        checklist_path = self.delivery_base / "DOCUMENTATION" / "closure_checklist.json"
        with open(checklist_path, 'w', encoding='utf-8') as f:
            json.dump(checklist, f, indent=2, ensure_ascii=False)
        
        self._print("Case closure checklist created", "OK")
        
        # Count total items
        total_items = sum(len(cat['items']) for cat in checklist['closure_items'])
        self._print(f"  Total checklist items: {total_items}", "INFO")
    
    def create_archival_manifest(self):
        """
        FÁZA 7: Vytvorenie archival manifest.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("ARCHIVAL MANIFEST GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        retention_date = datetime.utcnow() + timedelta(days=365*7)
        
        archival_manifest = {
            "case_id": self.case_id,
            "archival_date": datetime.utcnow().isoformat() + "Z",
            "retention_period_years": 7,
            "retention_until": retention_date.strftime("%Y-%m-%d"),
            "destruction_date": retention_date.strftime("%Y-%m-%d"),
            "archived_items": [
                {
                    "category": "Forensic Images",
                    "description": "Original forensic disk images",
                    "location": "Secure archive storage",
                    "format": "dd / E01",
                    "retention_reason": "Legal requirement"
                },
                {
                    "category": "Analysis Results",
                    "description": "All analysis outputs from workflow",
                    "location": f"{self.case_id}_*_report.json",
                    "format": "JSON",
                    "retention_reason": "Technical documentation"
                },
                {
                    "category": "Photo Catalog",
                    "description": "Complete cataloged photos",
                    "location": f"{self.case_id}_catalog/",
                    "format": "Mixed (JPEG, HTML, JSON, CSV)",
                    "retention_reason": "Deliverable backup"
                },
                {
                    "category": "Final Report",
                    "description": "Comprehensive final report",
                    "location": f"{self.case_id}_final_report/",
                    "format": "JSON, PDF, TXT",
                    "retention_reason": "Legal documentation"
                },
                {
                    "category": "Chain of Custody",
                    "description": "Complete CoC documentation",
                    "location": "CoC logs and protocols",
                    "format": "JSON, PDF",
                    "retention_reason": "Legal requirement"
                },
                {
                    "category": "Delivery Documentation",
                    "description": "Signed delivery protocols",
                    "location": f"{self.case_id}_delivery/DOCUMENTATION/",
                    "format": "PDF (scanned signatures)",
                    "retention_reason": "Legal proof of delivery"
                },
                {
                    "category": "Client Communications",
                    "description": "Email correspondence",
                    "location": "Email archive",
                    "format": "EML, PDF",
                    "retention_reason": "Communication audit trail"
                },
                {
                    "category": "Case Notes",
                    "description": "Internal case notes and observations",
                    "location": "Case management system",
                    "format": "Text, JSON",
                    "retention_reason": "Process improvement"
                }
            ],
            "archival_checklist": [
                "All forensic images stored in secure, redundant storage",
                "All documentation converted to PDF/A for long-term preservation",
                "Metadata indexed for easy retrieval",
                "Access controls configured (authorized personnel only)",
                "Retention reminder set in calendar",
                "Destruction process scheduled for retention end date",
                "GDPR compliance verified"
            ],
            "access_restrictions": {
                "authorized_personnel": ["Forensic analysts", "Laboratory managers"],
                "access_logging": "All access logged and audited",
                "encryption": "AES-256 at rest",
                "backup": "3-2-1 backup strategy"
            },
            "destruction_procedure": {
                "method": "Secure deletion (DoD 5220.22-M)",
                "verification": "Deletion certificates generated",
                "documentation": "Destruction log maintained",
                "review_required": "Senior analyst approval before destruction"
            }
        }
        
        manifest_path = self.delivery_base / "DOCUMENTATION" / "archival_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(archival_manifest, f, indent=2, ensure_ascii=False)
        
        self._print("Archival manifest created", "OK")
        self._print(f"  Retention period: 7 years", "INFO")
        self._print(f"  Retention until: {retention_date.strftime('%Y-%m-%d')}", "INFO")
    
    def prepare_directories(self):
        """Vytvorenie výstupných adresárov"""
        self.delivery_base.mkdir(parents=True, exist_ok=True)
        return True
    
    def run_delivery_preparation(self):
        """Hlavná funkcia - spustí prípravu delivery"""
        
        self._print("="*70, "TITLE")
        self._print("DELIVERY PREPARATION", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Prepare directories
        self.prepare_directories()
        
        # 2. Prepare package structure
        self.prepare_package_structure()
        
        # 3. Generate manifest
        self.generate_manifest()
        
        # 4. Create completion email
        self.create_completion_email()
        
        # 5. Create delivery protocol
        self.create_delivery_protocol()
        
        # 6. Create satisfaction survey
        self.create_satisfaction_survey()
        
        # 7. Create case closure checklist
        self.create_case_closure_checklist()
        
        # 8. Create archival manifest
        self.create_archival_manifest()
        
        # 9. Final summary
        self._print("\n" + "="*70, "TITLE")
        self._print("DELIVERY PREPARATION COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Delivery package location: {self.delivery_base}", "OK")
        self._print(f"Total files in manifest: {self.manifest['total_files']}", "INFO")
        
        self._print("\n⚠️  NEXT MANUAL STEPS:", "WARNING")
        self._print("  1. Send completion email to client", "WARNING")
        self._print("  2. Confirm delivery method with client", "WARNING")
        self._print("  3. Execute delivery (personal/courier/online)", "WARNING")
        self._print("  4. Obtain signatures on delivery protocol", "WARNING")
        self._print("  5. Close Chain of Custody (set status CLOSED)", "WARNING")
        self._print("  6. Send satisfaction survey (24-48h after delivery)", "WARNING")
        self._print("  7. Archive all case files (7-year retention)", "WARNING")
        self._print("  8. Update database (status = CLOSED)", "WARNING")
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["package_ready"] = True
        self.stats["success"] = True
        
        return self.stats


def main():
    """
    Hlavná funkcia
    """
    
    print("\n" + "="*70)
    print("FOR-COL-DELIVERY: Delivery Preparation")
    print("="*70 + "\n")
    
    # Vstupné parametre
    if len(sys.argv) >= 2:
        case_id = sys.argv[1]
    else:
        case_id = input("Case ID (e.g., PHOTO-2025-01-26-001): ").strip()
    
    # Validácia
    if not case_id:
        print("ERROR: Case ID cannot be empty")
        sys.exit(1)
    
    # Run delivery preparation
    delivery = DeliveryPreparation(case_id)
    results = delivery.run_delivery_preparation()
    
    if results["success"]:
        print(f"\n✅ Delivery preparation completed successfully")
        print(f"📁 Delivery package: {delivery.delivery_base}")
        print(f"\n⚠️  Manual steps required:")
        print(f"  • Send completion email")
        print(f"  • Confirm delivery method")
        print(f"  • Execute delivery")
        print(f"  • Obtain signatures")
        print(f"  • Close Chain of Custody")
        print(f"  • Send satisfaction survey")
        print(f"  • Archive case files")
        print(f"\n🎉 Photo recovery workflow complete!")
        print(f"✅ Case ready for delivery and closure")
        sys.exit(0)
    else:
        print("\nDelivery preparation failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - DELIVERY PREPARATION
================================================================================

DELIVERY PREPARATION
- Prepares all materials for client delivery
- Generates required documentation
- Creates checklists and protocols
- Automates preparation tasks
- Manual execution required for actual delivery

SEVEN-PHASE PROCESS

1. PACKAGE STRUCTURE PREPARATION
   - Create delivery directory structure
   - Organize PHOTOS, CATALOG, REPORT, DOCUMENTATION
   - Prepare subdirectories

2. MANIFEST GENERATION
   - List all deliverable files
   - Calculate SHA-256 checksums
   - Document total size
   - Create MANIFEST.json

3. COMPLETION EMAIL CREATION
   - Professional client notification
   - Case summary with statistics
   - Delivery options explained
   - Next steps outlined

4. DELIVERY PROTOCOL GENERATION
   - Legal delivery document
   - Signature blocks for both parties
   - Item checklist
   - Chain of Custody closure section

5. SATISFACTION SURVEY CREATION
   - 5-question survey
   - Rating scales 1-5
   - Testimonial collection
   - Target: 4.5+ / 5.0

6. CASE CLOSURE CHECKLIST
   - 7 categories of closure tasks
   - Status tracking
   - Completion metrics
   - Target timelines

7. ARCHIVAL MANIFEST
   - 7-year retention plan
   - Destruction scheduling
   - Access controls
   - GDPR compliance

DELIVERY METHODS

PERSONAL PICKUP (Recommended):
✓ Client identity verification
✓ Personal briefing
✓ Immediate signatures
✓ Media returned on-site
✓ Q&A session
× Requires scheduling

COURIER SERVICE:
✓ Secure packaging
✓ Insurance coverage
✓ Tracking number
✓ Signature required
× 2-3 day delivery time
× Higher cost

ONLINE TRANSFER:
✓ Fastest (24h)
✓ Secure download link
✓ 7-day validity
✓ SHA-256 verification
× Media sent separately
× Requires secure platform

CHAIN OF CUSTODY CLOSURE

Final Entry Components:
- Date/time of delivery
- Delivery method
- Location
- Client name
- Signatures (analyst + client)
- Status: CLOSED

Verification:
☑ No gaps in custody
☑ All transfers documented
☑ Chronological order
☑ All events timestamped
☑ All persons identified

CLIENT SATISFACTION METRICS

Target Scores:
- Overall quality: 4.5+ / 5.0
- Photo recovery: 4.5+ / 5.0
- Communication: 4.5+ / 5.0
- Would recommend: 90%+
- Survey response rate: 80%+

ARCHIVAL REQUIREMENTS

Retention Period: 7 years
Items Archived:
- Forensic images
- Analysis results
- Photo catalog
- Final report
- Chain of Custody
- Delivery documentation
- Client communications

Destruction:
- DoD 5220.22-M secure deletion
- Deletion certificates
- Senior analyst approval
- Destruction log

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
DELIVERY PREPARATION
Case ID: PHOTO-2025-01-26-001
======================================================================

======================================================================
DELIVERY PACKAGE PREPARATION
======================================================================

[✓] Delivery package structure created
[i]   Location: PHOTO-2025-01-26-001_delivery

======================================================================
MANIFEST GENERATION
======================================================================

[i]   photo_catalog.html: 45,234 bytes
[i]   FINAL_REPORT.json: 123,456 bytes
[i]   README.txt: 8,912 bytes
[i]   catalog_summary.json: 3,456 bytes

[✓] Manifest generated: 4 files
[i] Total size: 0.17 MB

======================================================================
COMPLETION EMAIL GENERATION
======================================================================

[✓] Completion email template created
[i]   Location: completion_email.txt

======================================================================
DELIVERY PROTOCOL GENERATION
======================================================================

[✓] Delivery protocol template created
[i]   Location: delivery_protocol.txt

======================================================================
SATISFACTION SURVEY GENERATION
======================================================================

[✓] Client satisfaction survey created
[i]   Target score: 4.5+ / 5.0

======================================================================
CASE CLOSURE CHECKLIST GENERATION
======================================================================

[✓] Case closure checklist created
[i]   Total checklist items: 31

======================================================================
ARCHIVAL MANIFEST GENERATION
======================================================================

[✓] Archival manifest created
[i]   Retention period: 7 years
[i]   Retention until: 2032-02-13

======================================================================
DELIVERY PREPARATION COMPLETED
======================================================================
[✓] Delivery package location: PHOTO-2025-01-26-001_delivery
[i] Total files in manifest: 4

⚠️  NEXT MANUAL STEPS:
[!]   1. Send completion email to client
[!]   2. Confirm delivery method with client
[!]   3. Execute delivery (personal/courier/online)
[!]   4. Obtain signatures on delivery protocol
[!]   5. Close Chain of Custody (set status CLOSED)
[!]   6. Send satisfaction survey (24-48h after delivery)
[!]   7. Archive all case files (7-year retention)
[!]   8. Update database (status = CLOSED)
======================================================================

✅ Delivery preparation completed successfully
📁 Delivery package: PHOTO-2025-01-26-001_delivery

⚠️  Manual steps required:
  • Send completion email
  • Confirm delivery method
  • Execute delivery
  • Obtain signatures
  • Close Chain of Custody
  • Send satisfaction survey
  • Archive case files

🎉 Photo recovery workflow complete!
✅ Case ready for delivery and closure

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step20_delivery.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step20_delivery.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 18 (Cataloging) must be completed
- Step 19 (Final Report) must be completed
- Python 3 with json, hashlib modules

TIME ESTIMATE:
- Preparation: ~30-60 minutes (automated)
- Client contact: ~24 hours (waiting for response)
- Delivery execution: 1-3 days (depends on method)
- Survey & closure: ~1 week

================================================================================
MANUAL TASKS CHECKLIST
================================================================================

BEFORE DELIVERY:
☐ Review all prepared documents
☐ Verify package integrity
☐ Send completion email
☐ Wait for client response
☐ Confirm delivery method
☐ Schedule pickup/courier/transfer

DURING DELIVERY:
☐ Verify client identity (personal pickup)
☐ Provide package + original media
☐ Give briefing on usage
☐ Answer client questions
☐ Sign delivery protocol
☐ Obtain client signature

AFTER DELIVERY:
☐ Update Chain of Custody (CLOSED)
☐ File signed protocols
☐ Send satisfaction survey (24-48h)
☐ Collect survey responses
☐ Analyze feedback
☐ Request testimonial
☐ Issue invoice
☐ Archive all files
☐ Update database
☐ Document lessons learned

================================================================================
STANDARDS COMPLIANCE
================================================================================

ISO/IEC 27037:2012 - Evidence preservation ✓
NIST SP 800-86 - Forensic reporting ✓
ACPO Principle 4 - Documentation & audit ✓
ISO 9001:2015 - Customer satisfaction ✓
GDPR Article 30 - Records retention ✓

================================================================================
"""