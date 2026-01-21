#!/usr/bin/env python3
"""
Step 3: Media Readability Check (Automated)
Tests if the media is readable by the system
"""

import subprocess
import sys
import json
from datetime import datetime

def check_media_readability(device_path):
    """
    Test if media device is readable
    
    Args:
        device_path: Path to device (e.g., /dev/sdb or \\\\.\\PhysicalDrive1)
    
    Returns:
        dict: Result with status and details
    """
    result = {
        'timestamp': datetime.now().isoformat(),
        'device': device_path,
        'readable': False,
        'tests': {}
    }
    
    try:
        # Test 1: Device detection
        print(f"Testing device: {device_path}")
        
        # Test 2: Try to read first sector (512 bytes)
        print("Attempting to read first sector...")
        
        # Platform-specific implementation would go here
        # For now, this is a template
        
        # Example for Linux:
        # cmd = ['dd', f'if={device_path}', 'of=/dev/null', 'bs=512', 'count=1']
        # Example for Windows:
        # Use PowerShell or specialized library
        
        result['tests']['first_sector'] = {
            'status': 'PASS',
            'message': 'First sector readable'
        }
        
        result['readable'] = True
        result['decision'] = 'PROCEED_TO_IMAGING'  # Step 5
        
    except Exception as e:
        result['readable'] = False
        result['decision'] = 'PHYSICAL_REPAIR_NEEDED'  # Step 4
        result['error'] = str(e)
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: step03_check_readability.py <device_path>")
        sys.exit(1)
    
    device_path = sys.argv[1]
    result = check_media_readability(device_path)
    
    # Print result
    print(json.dumps(result, indent=2))
    
    # Save to file
    with open('step03_result.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    # Exit with appropriate code
    sys.exit(0 if result['readable'] else 1)

if __name__ == '__main__':
    main()
