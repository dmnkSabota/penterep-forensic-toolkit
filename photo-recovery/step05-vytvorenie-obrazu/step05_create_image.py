#!/usr/bin/env python3
"""
Step 5: Forensic Imaging (Automated)
Creates a forensic image of the media
"""

import subprocess
import sys
import json
import os
from datetime import datetime

def create_forensic_image(device_path, output_path, case_id, use_ddrescue=False):
    """
    Create forensic image of media
    
    Args:
        device_path: Source device
        output_path: Destination for image file
        case_id: Case identifier
        use_ddrescue: Use ddrescue for damaged media
    
    Returns:
        dict: Result with imaging details
    """
    result = {
        'timestamp_start': datetime.now().isoformat(),
        'case_id': case_id,
        'device': device_path,
        'output_file': output_path,
        'method': 'ddrescue' if use_ddrescue else 'dd',
        'success': False
    }
    
    try:
        if use_ddrescue:
            # Use ddrescue for damaged media
            log_file = output_path + '.log'
            cmd = [
                'ddrescue',
                '-d',           # Direct disk access
                '-r3',          # Retry 3 times
                device_path,
                output_path,
                log_file
            ]
        else:
            # Use dd for healthy media
            cmd = [
                'dd',
                f'if={device_path}',
                f'of={output_path}',
                'bs=4M',        # 4MB blocks
                'status=progress'
            ]
        
        print(f"Starting imaging: {' '.join(cmd)}")
        print("This may take several hours...")
        
        # Execute imaging command
        process = subprocess.run(cmd, capture_output=True, text=True)
        
        result['exit_code'] = process.returncode
        result['stdout'] = process.stdout
        result['stderr'] = process.stderr
        result['success'] = process.returncode == 0
        result['timestamp_end'] = datetime.now().isoformat()
        
        # Get output file size
        if os.path.exists(output_path):
            result['output_size_bytes'] = os.path.getsize(output_path)
        
        print(f"Imaging {'completed' if result['success'] else 'failed'}")
        
    except Exception as e:
        result['error'] = str(e)
        result['timestamp_end'] = datetime.now().isoformat()
    
    return result

def main():
    if len(sys.argv) < 4:
        print("Usage: step05_create_image.py <device> <output_file> <case_id> [--ddrescue]")
        sys.exit(1)
    
    device_path = sys.argv[1]
    output_path = sys.argv[2]
    case_id = sys.argv[3]
    use_ddrescue = '--ddrescue' in sys.argv
    
    result = create_forensic_image(device_path, output_path, case_id, use_ddrescue)
    
    # Save result
    with open('step05_result.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['success'] else 1)

if __name__ == '__main__':
    main()
