#!/usr/bin/env python3
"""
Step 15: Photo Integrity Validation (Automated)
Validates recovered photos for corruption
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

def validate_image(image_path):
    """
    Validate image integrity
    
    Returns:
        dict: Validation result
    """
    try:
        # Try to open and verify
        img = Image.open(image_path)
        img.verify()
        
        # Reopen after verify (verify closes the file)
        img = Image.open(image_path)
        img.load()
        
        width, height = img.size
        
        if width == 0 or height == 0:
            return {
                'status': 'CORRUPTED',
                'error': 'Invalid dimensions'
            }
        
        return {
            'status': 'VALID',
            'width': width,
            'height': height,
            'mode': img.mode
        }
        
    except Exception as e:
        return {
            'status': 'CORRUPTED',
            'error': str(e)
        }

def validate_directory(photos_dir, case_id):
    """
    Validate all photos in directory
    """
    result = {
        'case_id': case_id,
        'timestamp': datetime.now().isoformat(),
        'directory': photos_dir,
        'total_files': 0,
        'validation_summary': {
            'valid': 0,
            'corrupted': 0,
            'partial_corruption': 0
        },
        'validation_results': [],
        'files_needing_repair': []
    }
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'}
    
    print(f"Validating photos in: {photos_dir}")
    
    for root, dirs, files in os.walk(photos_dir):
        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext not in image_extensions:
                continue
            
            result['total_files'] += 1
            filepath = os.path.join(root, filename)
            
            print(f"  Validating: {filename}", end="")
            
            validation = validate_image(filepath)
            
            entry = {
                'file_id': result['total_files'],
                'filename': filename,
                'path': filepath,
                'status': validation['status']
            }
            
            if validation['status'] == 'VALID':
                result['validation_summary']['valid'] += 1
                entry['details'] = {
                    'width': validation['width'],
                    'height': validation['height'],
                    'mode': validation['mode']
                }
                print(" ✓ VALID")
            else:
                result['validation_summary']['corrupted'] += 1
                result['files_needing_repair'].append(result['total_files'])
                entry['error'] = validation['error']
                print(f" ✗ CORRUPTED ({validation['error']})")
            
            result['validation_results'].append(entry)
    
    return result

def main():
    if len(sys.argv) < 3:
        print("Usage: step15_validate_integrity.py <photos_directory> <case_id>")
        sys.exit(1)
    
    photos_dir = sys.argv[1]
    case_id = sys.argv[2]
    
    if not os.path.exists(photos_dir):
        print(f"Error: Directory not found: {photos_dir}")
        sys.exit(1)
    
    result = validate_directory(photos_dir, case_id)
    
    print(f"\nValidation complete:")
    print(f"  Total files: {result['total_files']}")
    print(f"  Valid: {result['validation_summary']['valid']}")
    print(f"  Corrupted: {result['validation_summary']['corrupted']}")
    
    success_rate = result['validation_summary']['valid'] / result['total_files'] if result['total_files'] > 0 else 0
    print(f"  Success rate: {success_rate:.1%}")
    
    # Save result
    output_file = f'step15_{case_id}_validation.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    sys.exit(0)

if __name__ == '__main__':
    main()
