# reference_values.sh
#
# Reference constants used by the ptforensicanalysis unit test suite.
# Every value in this file is traceable to a published standard or to a
# value computable from first principles; no constant is derived from the
# implementation under test. Each value can therefore be independently
# verified against the cited source.
#
# This file is sourced, not executed:
#       source "${SCRIPT_DIR}/testlib/reference_values.sh"
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0 (matches parent project)

# Re-sourcing guard so multiple includes in a single shell are harmless.
[ -n "${_REFVALS_SOURCED:-}" ] && return 0
_REFVALS_SOURCED=1


# =============================================================================
# 1. SHA-256 test vectors
#
# Source: NIST FIPS PUB 180-4, "Secure Hash Standard (SHS)", August 2015.
#         Appendix B contains worked examples for SHA-256.
# Online reference: https://csrc.nist.gov/projects/cryptographic-standards-and-
#                   guidelines/example-values
#
# Each value below may be reproduced from a Linux shell, e.g.
#       printf 'abc' | sha256sum
# =============================================================================

# Empty string
NIST_SHA256_EMPTY="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# "abc"  (FIPS 180-4 Appendix B.1)
NIST_SHA256_ABC="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

# "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
# (FIPS 180-4 Appendix B.2; 448 bits, exercises padding boundary)
NIST_SHA256_LONG="248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"

# One million repetitions of "a" (FIPS 180-4 Appendix B.3; large input)
NIST_SHA256_MILLION_A="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"

# A deterministically distinct hash used to construct hash-mismatch cases.
# Computed from the literal byte sequence "mismatch":
#       printf 'mismatch' | sha256sum
REF_SHA256_MISMATCH="5acbfff1b086e0f920c5857527976199018afe0cbf16e28d42c7eb9c683508e5"

# A string consisting of 64 'f' hex characters. Syntactically valid
# as SHA-256 but cryptographically impossible to collide with a real file.
REF_SHA256_ALL_F="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


# =============================================================================
# 2. Image format magic bytes / signatures
#
# Sources:
#   - JPEG: ISO/IEC 10918-1:1994, Sec. B.1.1.3 (Markers)
#   - PNG:  ISO/IEC 15948:2004,   Sec. 5.2  (PNG signature)
#   - TIFF: TIFF 6.0 Specification (Adobe, June 1992), Sec. 2 (Header)
#   - GIF:  GIF89a Specification (CompuServe, July 1990)
#   - BMP:  Microsoft Windows Bitmap File Format (BITMAPFILEHEADER)
# =============================================================================

JPEG_SOI_MARKER='\xff\xd8'         # Start of Image (must be first 2 bytes)
JPEG_EOI_MARKER='\xff\xd9'         # End of Image   (must be last  2 bytes)
PNG_SIGNATURE='\x89PNG\r\n\x1a\n'  # 8-byte fixed signature
TIFF_LE_SIGNATURE='II*\x00'        # Little-endian (Intel) byte order
TIFF_BE_SIGNATURE='MM\x00*'        # Big-endian (Motorola) byte order
GIF_SIGNATURE_87='GIF87a'
GIF_SIGNATURE_89='GIF89a'
BMP_SIGNATURE='BM'


# =============================================================================
# 3. Standard exit codes (mirrors thesis Table 4.4)
#
# These mirror the exit code convention declared in the toolkit. Listed here
# so tests assert against named constants instead of bare integers, which
# makes regression to a different value detectable.
# =============================================================================

EXIT_SUCCESS=0     # nominal completion (VERIFIED, READABLE, gate PASS)
EXIT_FAILURE=1     # processing error or forensic finding (MISMATCH, 0 files)
EXIT_FINDING=2     # specific finding (UNREADABLE media)
EXIT_ENV=99        # environment error (missing tool, write-blocker rejected)
EXIT_SIGNAL=130    # interrupted by SIGINT (128 + 2)


# =============================================================================
# 4. Threshold constants (mirrors thesis Table 4.2, module _constants)
#
# Duplicated deliberately. If production code mutates one of these values,
# unit tests in category C (boundary cases) will fail immediately, which
# prevents silent regression of forensic semantics.
# =============================================================================

REF_MIN_IMAGE_BYTES=100              # below this size: classify as 'invalid'
REF_CORRUPT_SIZE_THRESHOLD=1024      # boundary between 'corrupted' and 'invalid'
REF_HASH_BLOCK_SIZE=4194304          # 4 MiB SHA-256 streaming block
REF_VALIDATE_TIMEOUT=30              # seconds, per-file validation budget
REF_VT_REQUEST_DELAY=15              # VirusTotal free-tier rate limit
REF_VT_MAX_HASHES=10                 # VirusTotal hash queries per run
REF_VT_MAX_IPS=5                     # VirusTotal IP queries per run


# =============================================================================
# 5. Case ID prefixes (mirrors CASE_PREFIX_MAP in ptcocmanager)
#
# The first segment of the case identifier triggers automatic scenario
# detection in ptcocmanager. Tests use the constants here rather than
# string literals, so a rename in production code surfaces as a test diff.
# =============================================================================

PREFIX_COC="COC"
PREFIX_PHOTO="PHOTORECOVERY"
PREFIX_MALWARE="MALWARE"


# =============================================================================
# 6. Reserved IP ranges for test fixtures
#
# Source: RFC 5737, "IPv4 Address Blocks Reserved for Documentation".
# These ranges are guaranteed by IANA to be non-routable on the public
# Internet, so malware test fixtures cannot accidentally contact a real
# host even if a network were available.
# =============================================================================

RFC5737_TEST_NET_1="192.0.2.0/24"
RFC5737_TEST_NET_2="198.51.100.0/24"
RFC5737_TEST_NET_3="203.0.113.0/24"


# =============================================================================
# 7. Standard reserved hostnames
#
# Source: RFC 2606, "Reserved Top Level DNS Names".
# Domains under .example, .test, .invalid never resolve in production DNS
# and are safe to embed in malware test fixtures.
# =============================================================================

RFC2606_EXAMPLE_TLD="example.com"
RFC2606_TEST_TLD="test"
RFC2606_INVALID_TLD="invalid"