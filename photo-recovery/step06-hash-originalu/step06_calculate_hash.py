#!/usr/bin/env python3
"""
Step 6: Calculate SHA-256 Hash of Original Media (Automated)
"""

import hashlib
import sys
import json
from datetime import datetime

def calculate_hash(file_path, block_size=4096*1024):
    """
    Calculate SHA-256 hash of a file/device
    
    Args:
        file_path: Path to file or device
        block_size: Size of blocks to read (4MB default)
    
    Returns:
        str: SHA-256 hash hexdigest
    """
    sha256 = hashlib.sha256()
    total_bytes = 0
    
    print(f"Calculating SHA-256 hash of {file_path}...")
    print("This may take a while...")
    
    try:
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(block_size)
                if not data:
                    break
                sha256.update(data)
                total_bytes += len(data)
                
                # Progress indicator every 1GB
                if total_bytes % (1024*1024*1024) == 0:
                    print(f"  Processed: {total_bytes // (1024*1024*1024)} GB")
        
        return sha256.hexdigest()
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    if len(sys.argv) < 3:
        print("Usage: step06_calculate_hash.py <device_or_file> <case_id>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    case_id = sys.argv[2]
    
    result = {
        'case_id': case_id,
        'file_path': file_path,
        'timestamp_start': datetime.now().isoformat(),
        'hash_algorithm': 'SHA-256'
    }
    
    hash_value = calculate_hash(file_path)
    
    result['timestamp_end'] = datetime.now().isoformat()
    result['hash_value'] = hash_value
    result['success'] = hash_value is not None
    
    print(f"\nSHA-256: {hash_value}")
    
    # Save result
    with open(f'step06_{case_id}_hash.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['success'] else 1)

if __name__ == '__main__':
    main()
