#!/usr/bin/env python3.13
"""
Comprehensive test script for Pyre QT menu functionality.
Tests:
1. Transform conversions in all directions (Rigid <-> Grid <-> Mesh <-> RBF)
2. Control point operations (add/move/delete)
3. Save/Load functionality
4. Loading .stos files from URLs
"""

import os
import sys
import tempfile
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

# Add workspace to path
sys.path.insert(0, '/workspace')

import numpy as np
from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms as transforms
from nornir_imageregistration.transforms import TransformType


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.YELLOW}ℹ {text}{Colors.RESET}")


def download_file(url: str, dest_path: str) -> bool:
    """Download a file from URL to destination path"""
    try:
        print_info(f"Downloading {url}")
        urllib.request.urlretrieve(url, dest_path)
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            print_success(f"Downloaded to {dest_path}")
            return True
        else:
            print_error(f"Download failed or file is empty: {dest_path}")
            return False
    except Exception as e:
        print_error(f"Failed to download {url}: {e}")
        return False


def download_stos_and_images(stos_url: str, work_dir: str) -> Optional[str]:
    """
    Download a .stos file and its referenced images from a URL.
    Returns the path to the downloaded .stos file if successful.
    """
    print_header("Downloading STOS File and Images")
    
    # Download the .stos file
    stos_filename = os.path.basename(urllib.parse.urlparse(stos_url).path)
    stos_path = os.path.join(work_dir, stos_filename)
    
    if not download_file(stos_url, stos_path):
        return None
    
    # Parse the .stos file to get image paths
    try:
        with open(stos_path, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                print_error("Invalid .stos file format")
                return None
            
            # First two lines are image paths (relative to .stos file)
            target_image_rel = lines[0].strip()
            source_image_rel = lines[1].strip()
            
            # Convert Windows paths to URL paths
            target_image_rel = target_image_rel.replace('\\', '/')
            source_image_rel = source_image_rel.replace('\\', '/')
            
            # Get base URL
            base_url = stos_url.rsplit('/', 1)[0]
            
            # Construct image URLs
            target_image_url = urllib.parse.urljoin(base_url + '/', target_image_rel)
            source_image_url = urllib.parse.urljoin(base_url + '/', source_image_rel)
            
            # Download images
            target_image_path = os.path.join(work_dir, os.path.basename(target_image_rel))
            source_image_path = os.path.join(work_dir, os.path.basename(source_image_rel))
            
            if not download_file(target_image_url, target_image_path):
                print_error(f"Failed to download target image")
                return None
                
            if not download_file(source_image_url, source_image_path):
                print_error(f"Failed to download source image")
                return None
            
            # Update .stos file with local paths
            lines[0] = os.path.basename(target_image_rel) + '\n'
            lines[1] = os.path.basename(source_image_rel) + '\n'
            
            # Check for mask files (lines 9-10)
            if len(lines) >= 10 and lines[7].strip() == 'two_user_supplied_masks:':
                target_mask_rel = lines[8].strip()
                source_mask_rel = lines[9].strip()
                
                if target_mask_rel and source_mask_rel:
                    target_mask_rel = target_mask_rel.replace('\\', '/')
                    source_mask_rel = source_mask_rel.replace('\\', '/')
                    
                    target_mask_url = urllib.parse.urljoin(base_url + '/', target_mask_rel)
                    source_mask_url = urllib.parse.urljoin(base_url + '/', source_mask_rel)
                    
                    target_mask_path = os.path.join(work_dir, os.path.basename(target_mask_rel))
                    source_mask_path = os.path.join(work_dir, os.path.basename(source_mask_rel))
                    
                    if download_file(target_mask_url, target_mask_path):
                        lines[8] = os.path.basename(target_mask_rel) + '\n'
                    if download_file(source_mask_url, source_mask_path):
                        lines[9] = os.path.basename(source_mask_rel) + '\n'
            
            # Write updated .stos file
            with open(stos_path, 'w') as f:
                f.writelines(lines)
            
            print_success(f"Successfully prepared .stos file at {stos_path}")
            return stos_path
            
    except Exception as e:
        print_error(f"Failed to process .stos file: {e}")
        return None


def test_transform_conversions():
    """Test transform conversions in all directions"""
    print_header("Testing Transform Conversions")
    
    # Create a simple triangulation transform with control points
    # Format: [controlx controly warpedx warpedy]
    pointpairs = np.array([
        [100, 100, 105, 102],
        [200, 100, 205, 103],
        [100, 200, 102, 205],
        [200, 200, 203, 206]
    ], dtype=np.float64)
    
    initial_transform = transforms.Triangulation(pointpairs)
    
    # Define conversion paths to test
    conversion_paths = [
        (TransformType.MESH, TransformType.RIGID),
        (TransformType.RIGID, TransformType.GRID),
        (TransformType.GRID, TransformType.MESH),
        (TransformType.MESH, TransformType.RBF),
        (TransformType.RBF, TransformType.GRID),
        (TransformType.GRID, TransformType.RIGID),
        (TransformType.RIGID, TransformType.MESH),
        (TransformType.MESH, TransformType.GRID),
        (TransformType.GRID, TransformType.RBF),
        (TransformType.RBF, TransformType.RIGID),
    ]
    
    results = []
    source_image_shape = (1000, 1000)
    
    for from_type, to_type in conversion_paths:
        try:
            # Start with initial transform and convert to from_type
            from_kwargs = {"source_image_shape": source_image_shape}
            to_kwargs = {"source_image_shape": source_image_shape}
            
            # Add cell_size only when converting TO Grid
            if from_type == TransformType.GRID:
                from_kwargs["cell_size"] = (64, 64)
            if to_type == TransformType.GRID:
                to_kwargs["cell_size"] = (64, 64)
            
            if initial_transform.type != from_type:
                current_transform = transforms.ConvertTransform(
                    initial_transform, 
                    from_type,
                    **from_kwargs
                )
            else:
                current_transform = initial_transform
            
            # Convert to target type
            converted = transforms.ConvertTransform(
                current_transform, 
                to_type,
                **to_kwargs
            )
            
            # Verify the conversion
            if converted.type == to_type:
                print_success(f"{from_type.value} → {to_type.value}")
                results.append((from_type.value, to_type.value, True, None))
            else:
                print_error(f"{from_type.value} → {to_type.value}: Wrong type after conversion")
                results.append((from_type.value, to_type.value, False, "Wrong type"))
                
        except Exception as e:
            print_error(f"{from_type.value} → {to_type.value}: {str(e)}")
            results.append((from_type.value, to_type.value, False, str(e)))
    
    # Print summary
    print(f"\n{Colors.BOLD}Conversion Summary:{Colors.RESET}")
    successful = sum(1 for r in results if r[2])
    total = len(results)
    print(f"Successful: {successful}/{total}")
    
    if successful < total:
        print(f"\n{Colors.BOLD}Failed Conversions:{Colors.RESET}")
        for from_t, to_t, success, error in results:
            if not success:
                print(f"  {from_t} → {to_t}: {error}")
    
    return successful == total


def test_control_point_operations():
    """Test control point add/move/delete operations"""
    print_header("Testing Control Point Operations")
    
    # Create initial transform with control points
    # Format: [controlx controly warpedx warpedy]
    pointpairs = np.array([
        [100, 100, 105, 102],
        [200, 100, 205, 103],
        [100, 200, 102, 205]
    ], dtype=np.float64)
    
    transform = transforms.Triangulation(pointpairs)
    
    results = []
    
    # Test 1: Add control points
    try:
        new_pointpair = np.array([[150, 150, 155, 152]], dtype=np.float64)
        
        # Use the AddPoint method
        initial_count = len(transform.points)
        index = transform.AddPoint(new_pointpair[0])
        
        if len(transform.points) == initial_count + 1:
            print_success("Add control point")
            results.append(("Add", True, None))
        else:
            print_error("Add control point: Point count mismatch")
            results.append(("Add", False, "Point count mismatch"))
    except Exception as e:
        print_error(f"Add control point: {str(e)}")
        results.append(("Add", False, str(e)))
    
    # Test 2: Move control points
    try:
        # Get original position
        original_point = transform.points[0].copy()
        original_mapped = original_point[2:4].copy()
        
        # Move the first control point in target space
        new_mapped_pos = original_mapped + np.array([10, 10])
        new_pointpair = np.array([original_point[0], original_point[1], new_mapped_pos[0], new_mapped_pos[1]])
        transform.UpdatePointPair(0, new_pointpair)
        
        # Check if it moved
        current_mapped = transform.points[0, 2:4]
        if not np.allclose(current_mapped, original_mapped):
            print_success("Move control point")
            results.append(("Move", True, None))
        else:
            print_error("Move control point: Point didn't move")
            results.append(("Move", False, "Point didn't move"))
    except Exception as e:
        print_error(f"Move control point: {str(e)}")
        results.append(("Move", False, str(e)))
    
    # Test 3: Delete control points
    try:
        # Create a fresh transform for deletion test
        test_pointpairs = np.array([
            [100, 100, 105, 102],
            [200, 100, 205, 103],
            [100, 200, 102, 205],
            [200, 200, 203, 206]
        ], dtype=np.float64)
        delete_transform = transforms.Triangulation(test_pointpairs)
        
        initial_count = len(delete_transform.points)
        delete_transform.RemovePoint(0)
        
        if len(delete_transform.points) == initial_count - 1:
            print_success("Delete control point")
            results.append(("Delete", True, None))
        else:
            print_error("Delete control point: Point count mismatch")
            results.append(("Delete", False, "Point count mismatch"))
    except Exception as e:
        print_error(f"Delete control point: {str(e)}")
        results.append(("Delete", False, str(e)))
    
    # Print summary
    print(f"\n{Colors.BOLD}Control Point Operations Summary:{Colors.RESET}")
    successful = sum(1 for r in results if r[1])
    total = len(results)
    print(f"Successful: {successful}/{total}")
    
    return successful == total


def test_save_load(work_dir: str):
    """Test save and load functionality"""
    print_header("Testing Save/Load Functionality")
    
    results = []
    
    # Create test transform
    pointpairs = np.array([
        [100, 100, 105, 102],
        [200, 100, 205, 103],
        [100, 200, 102, 205],
        [200, 200, 203, 206]
    ], dtype=np.float64)
    transform = transforms.Triangulation(pointpairs)
    
    # Test saving and loading for each transform type
    for transform_type in [TransformType.MESH, TransformType.RIGID, TransformType.GRID, TransformType.RBF]:
        try:
            # Convert to target type
            kwargs = {"source_image_shape": (1000, 1000)}
            if transform_type == TransformType.GRID:
                kwargs["cell_size"] = (64, 64)
                
            if transform.type != transform_type:
                converted = transforms.ConvertTransform(
                    transform, 
                    transform_type,
                    **kwargs
                )
            else:
                converted = transform
            
            # Create a temporary .stos file
            stos_path = os.path.join(work_dir, f"test_{transform_type.value}.stos")
            
            # Create dummy image paths (we're just testing the transform save/load)
            target_image = "target.png"
            source_image = "source.png"
            
            # Save - need to convert to ITK string format
            transform_string = converted.ToITKString()
            
            # Create a simple stos file manually
            with open(stos_path, 'w') as f:
                f.write(f"{target_image}\n")
                f.write(f"{source_image}\n")
                f.write("0\n")  # ControlImageDim X
                f.write("0\n")  # ControlImageDim Y
                f.write("1 1 1000 1000\n")  # ControlBoundingBox
                f.write("1 1 1000 1000\n")  # MappedBoundingBox
                f.write(f"{transform_string}\n")
            
            if not os.path.exists(stos_path):
                print_error(f"Save {transform_type.value}: File not created")
                results.append((transform_type.value, False, "File not created"))
                continue
            
            # Load
            stos_obj = StosFile.Load(stos_path)
            loaded_transform = transforms.LoadTransform(stos_obj.Transform)
            
            # Verify
            if loaded_transform.type == transform_type:
                print_success(f"Save/Load {transform_type.value}")
                results.append((transform_type.value, True, None))
            else:
                print_error(f"Save/Load {transform_type.value}: Type mismatch after load")
                results.append((transform_type.value, False, "Type mismatch"))
                
        except Exception as e:
            print_error(f"Save/Load {transform_type.value}: {str(e)}")
            results.append((transform_type.value, False, str(e)))
    
    # Print summary
    print(f"\n{Colors.BOLD}Save/Load Summary:{Colors.RESET}")
    successful = sum(1 for r in results if r[1])
    total = len(results)
    print(f"Successful: {successful}/{total}")
    
    return successful == total


def test_url_loading(stos_url: str, work_dir: str):
    """Test loading .stos file from URL"""
    print_header("Testing URL Loading")
    
    try:
        stos_path = download_stos_and_images(stos_url, work_dir)
        
        if stos_path is None:
            print_error("Failed to download .stos file and images")
            return False
        
        # Try to load the .stos file
        stos_obj = StosFile.Load(stos_path)
        
        if stos_obj is None:
            print_error("Failed to load .stos file")
            return False
        
        print_success(f"Loaded .stos file: {stos_path}")
        print_info(f"Transform type: {stos_obj.Transform}")
        
        # Try to load the transform
        transform = transforms.LoadTransform(stos_obj.Transform)
        print_success(f"Loaded transform of type: {transform.type.value}")
        
        return True
        
    except Exception as e:
        print_error(f"URL loading failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test runner"""
    print_header("Pyre QT Menu Functionality - Comprehensive Test Suite")
    
    # Create temporary work directory
    work_dir = tempfile.mkdtemp(prefix="pyre_test_")
    print_info(f"Working directory: {work_dir}")
    
    try:
        results = {}
        
        # Run all tests
        results['transform_conversions'] = test_transform_conversions()
        results['control_points'] = test_control_point_operations()
        results['save_load'] = test_save_load(work_dir)
        
        # Test URL loading with the provided sample
        stos_url = "http://rogue1.codepharm.net/RC2/TEM/Grid16/401-402_ctrl-TEM_Leveled_map-TEM_Leveled.stos"
        results['url_loading'] = test_url_loading(stos_url, work_dir)
        
        # Print final summary
        print_header("Final Test Summary")
        
        total_tests = len(results)
        passed_tests = sum(1 for v in results.values() if v)
        
        for test_name, passed in results.items():
            status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
            print(f"{test_name:30s}: {status}")
        
        print(f"\n{Colors.BOLD}Overall: {passed_tests}/{total_tests} test categories passed{Colors.RESET}")
        
        if passed_tests == total_tests:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ All tests passed!{Colors.RESET}")
            return 0
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ Some tests failed{Colors.RESET}")
            return 1
            
    finally:
        # Cleanup
        if os.path.exists(work_dir):
            print_info(f"Cleaning up work directory: {work_dir}")
            shutil.rmtree(work_dir)


if __name__ == "__main__":
    sys.exit(main())
