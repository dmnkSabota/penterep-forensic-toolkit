#!/usr/bin/env python3
"""
Step 9: Hash Verification (Automated Decision Point)
Compares original and image hashes
"""

import sys
import json
from datetime import datetime

def verify_hashes(original_hash, image_hash, case_id):
    """
    Compare two hash values
    
    Returns:
        dict: Verification result
    """
    result = {
        'case_id': case_id,
        'timestamp': datetime.now().isoformat(),
        'original_hash': original_hash,
        'image_hash': image_hash,
        'match': original_hash == image_hash,
        'integrity_verified': original_hash == image_hash
    }
    
    if result['match']:
        result['decision'] = 'PROCEED_TO_ANALYSIS'  # Step 10
        result['next_step'] = '10_filesystem_analysis'
        result['message'] = 'Hash verification PASSED. Integrity confirmed.'
    else:
        result['decision'] = 'REPEAT_IMAGING'  # Back to Step 5
        result['next_step'] = '5_create_image_retry'
        result['message'] = 'Hash verification FAILED. Image does not match original.'
        result['action_required'] = 'Repeat imaging process'
    
    return result

def main():
    if len(sys.argv) < 4:
        print("Usage: step09_verify_hashes.py <original_hash> <image_hash> <case_id>")
        sys.exit(1)
    
    original_hash = sys.argv[1]
    image_hash = sys.argv[2]
    case_id = sys.argv[3]
    
    result = verify_hashes(original_hash, image_hash, case_id)
    
    # Print result
    print("="*60)
    print("HASH VERIFICATION RESULT")
    print("="*60)
    print(f"Original: {result['original_hash']}")
    print(f"Image:    {result['image_hash']}")
    print(f"Match:    {'✓ YES' if result['match'] else '✗ NO'}")
    print(f"Decision: {result['decision']}")
    print("="*60)
    
    # Save result
    with open(f'step09_{case_id}_verification.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['match'] else 1)

if __name__ == '__main__':
    main()
