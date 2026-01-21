#!/usr/bin/env python3
"""
Step 14: EXIF Analysis (Automated)
Extracts EXIF metadata from recovered photos
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
except ImportError:
    print("Error: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

def extract_exif(image_path):
    """
    Extract EXIF data from image
    
    Returns:
        dict: EXIF data or None
    """
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if not exif_data:
            return None
        
        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = str(value)
        
        return exif
        
    except Exception as e:
        return None

def extract_gps(exif):
    """
    Extract GPS coordinates from EXIF
    """
    if 'GPSInfo' not in exif:
        return None
    
    gps_info = exif['GPSInfo']
    gps_data = {}
    
    for tag_id, value in gps_info.items():
        tag = GPSTAGS.get(tag_id, tag_id)
        gps_data[tag] = value
    
    return gps_data

def analyze_directory(photos_dir, case_id):
    """
    Analyze all photos in directory
    """
    result = {
        'case_id': case_id,
        'timestamp': datetime.now().isoformat(),
        'directory': photos_dir,
        'total_files': 0,
        'files_with_exif': 0,
        'files_without_exif': 0,
        'exif_data': []
    }
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    
    print(f"Analyzing photos in: {photos_dir}")
    
    for root, dirs, files in os.walk(photos_dir):
        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext not in image_extensions:
                continue
            
            result['total_files'] += 1
            filepath = os.path.join(root, filename)
            
            print(f"  Processing: {filename}")
            
            exif = extract_exif(filepath)
            
            entry = {
                'file_id': result['total_files'],
                'filename': filename,
                'path': filepath,
                'exif_present': exif is not None
            }
            
            if exif:
                result['files_with_exif'] += 1
                entry['exif'] = {
                    'make': exif.get('Make'),
                    'model': exif.get('Model'),
                    'datetime_original': exif.get('DateTimeOriginal'),
                    'iso': exif.get('ISOSpeedRatings'),
                    'exposure_time': exif.get('ExposureTime'),
                    'f_number': exif.get('FNumber'),
                    'focal_length': exif.get('FocalLength'),
                    'width': exif.get('ExifImageWidth'),
                    'height': exif.get('ExifImageHeight'),
                }
                # Filter out None values
                entry['exif'] = {k: v for k, v in entry['exif'].items() if v is not None}
            else:
                result['files_without_exif'] += 1
                entry['exif'] = None
            
            result['exif_data'].append(entry)
    
    return result

def main():
    if len(sys.argv) < 3:
        print("Usage: step14_exif_analysis.py <photos_directory> <case_id>")
        sys.exit(1)
    
    photos_dir = sys.argv[1]
    case_id = sys.argv[2]
    
    if not os.path.exists(photos_dir):
        print(f"Error: Directory not found: {photos_dir}")
        sys.exit(1)
    
    result = analyze_directory(photos_dir, case_id)
    
    print(f"\nAnalysis complete:")
    print(f"  Total files: {result['total_files']}")
    print(f"  With EXIF: {result['files_with_exif']}")
    print(f"  Without EXIF: {result['files_without_exif']}")
    
    # Save result
    output_file = f'step14_{case_id}_exif.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    sys.exit(0)

if __name__ == '__main__':
    main()
