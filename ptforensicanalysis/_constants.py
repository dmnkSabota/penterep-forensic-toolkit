#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    _constants - Shared constants for photo-recovery and malware forensic tools
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""
from typing import Dict, FrozenSet, List, Tuple

DEFAULT_OUTPUT_DIR = "/var/forensics/images"

IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".heic", ".heif", ".webp",
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".raf", ".rw2", ".pef", ".raw",
})

IMAGE_FILE_KEYWORDS: FrozenSet[str] = frozenset({
    "image", "jpeg", "png", "tiff", "gif", "bitmap",
    "raw", "canon", "nikon", "exif", "webp", "heic",
})

FORMAT_GROUP_MAP: Dict[str, str] = {
    "jpg": "jpeg",  "jpeg": "jpeg",
    "png": "png",
    "tif": "tiff",  "tiff": "tiff",
    "gif": "other", "bmp":  "other",
    "heic": "other", "heif": "other", "webp": "other",
    "cr2": "raw",  "cr3": "raw",  "nef": "raw",  "nrw": "raw",
    "arw": "raw",  "srf": "raw",  "sr2": "raw",  "dng": "raw",
    "orf": "raw",  "raf": "raw",  "rw2": "raw",  "pef": "raw",  "raw": "raw",
}

MIN_IMAGE_BYTES = 100
CORRUPT_SIZE_THRESHOLD = 1024
HASH_BLOCK_SIZE = 4 * 1024 * 1024

MMLS_TIMEOUT = 60
FSSTAT_TIMEOUT = 60
FLS_TIMEOUT = 600
FLS_RECOVERY_TIMEOUT = 1800
ICAT_TIMEOUT = 60
EXIF_TIMEOUT = 30
VALIDATE_TIMEOUT = 30
PHOTOREC_TIMEOUT = 14400

FS_TYPE_MAP: Dict[str, str] = {
    "FAT32": "FAT32",  "FAT16": "FAT16",  "FAT12": "FAT12",
    "exFAT": "exFAT",  "NTFS":  "NTFS",
    "Ext4": "ext4",    "ext4":  "ext4",   "Ext3": "ext3",  "ext3": "ext3",
    "Ext2": "ext2",    "ext2":  "ext2",   "HFS+": "HFS+",  "APFS": "APFS",
    "ISO 9660": "ISO9660",
}

RECOVERY_STRATEGIES: Dict[Tuple[bool, bool], Tuple[str, str, int, List[str]]] = {
    (True, True): (
        "filesystem_scan",
        "fls + icat (The Sleuth Kit)",
        15,
        [
            "Filesystem intact - filesystem-based scan recommended.",
            "Original filenames and directory structure preserved.",
            "Fastest recovery method.",
        ],
    ),
    (True, False): (
        "hybrid",
        "fls + photorec",
        60,
        [
            "Filesystem recognised but directory structure damaged.",
            "Hybrid: filesystem scan + file carving on unallocated space.",
            "Some filenames may be lost.",
        ],
    ),
    (False, True): (
        "file_carving",
        "photorec / foremost",
        90,
        [
            "Filesystem not recognised - directory listing unreliable.",
            "File carving required (signature-based recovery).",
            "Original filenames and directory structure will be lost.",
        ],
    ),
    (False, False): (
        "file_carving",
        "photorec / foremost",
        90,
        [
            "Filesystem not recognised or severely damaged.",
            "File carving required (signature-based recovery).",
            "Original filenames and directory structure will be lost.",
        ],
    ),
}

DEFAULT_VOLATILE_OUTPUT_DIR = "/var/forensics/volatile"
DEFAULT_ANALYSIS_OUTPUT_DIR = "/var/forensics/analysis"
DEFAULT_MOUNT_BASE = "/mnt/forensic"

SUSPICIOUS_EXTENSIONS: Tuple[str, ...] = (
    "*.exe", "*.dll", "*.sys", "*.bat", "*.cmd", "*.ps1",
    "*.vbs", "*.js", "*.hta", "*.scr", "*.pif", "*.com",
    "*.msi", "*.jar", "*.sh",
)

SUSPICIOUS_SCAN_PATHS: Tuple[str, ...] = (
    "Temp", "tmp", "AppData/Roaming", "AppData/Local/Temp",
    "ProgramData", "Users/Public", "Windows/Temp",
)

PRIVATE_IP_PREFIXES: Tuple[str, ...] = (
    "10.", "192.168.", "127.", "0.0.0.", "255.", "169.254.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.",
    "172.31.",
)

WIN_AUTOSTART_PATHS: Tuple[str, ...] = (
    "SOFTWARE/Microsoft/Windows/CurrentVersion/Run",
    "SOFTWARE/Microsoft/Windows/CurrentVersion/RunOnce",
    "SOFTWARE/Microsoft/Windows NT/CurrentVersion/Winlogon",
    "SYSTEM/CurrentControlSet/Services",
    "SOFTWARE/Microsoft/Windows/CurrentVersion/Policies/Explorer/Run",
)

PACKER_KEYWORDS: Tuple[str, ...] = (
    "upx", "packed", "peid", "themida", "aspack", "upack", "pecompact",
)

OBFUSCATION_KEYWORDS: Tuple[str, ...] = (
    "base64", "xor", "fromcharcode", "charcodeat", "eval(", "exec(",
)

RAM_TIMEOUT = 600
STATIC_STRINGS_TIMEOUT = 60
PCAP_TIMEOUT = 120
REGISTRY_TIMEOUT = 30
VT_REQUEST_DELAY = 15
VT_MAX_HASHES = 10
VT_MAX_IPS = 5
MAX_SUSPICIOUS_FILES = 200