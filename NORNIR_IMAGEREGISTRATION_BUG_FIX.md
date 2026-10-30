# Bug Fix for nornir_imageregistration v1.6.5

## Issue
Rigid transforms cannot be loaded from saved STOS files due to parameter name mismatch.

## Error Message
```
TypeError: CenteredSimilarity2DTransform.__init__() got an unexpected keyword argument 'scale'. 
Did you mean 'scalar'?
```

## Root Cause
In `nornir_imageregistration/transforms/factory.py`, the `ParseCenteredSimilarity2DTransform()` function uses the wrong parameter name when constructing a `CenteredSimilarity2DTransform` object.

## Location
**File**: `nornir_imageregistration/transforms/factory.py`  
**Function**: `ParseCenteredSimilarity2DTransform()`  
**Approximate Line**: 448

## Current Code (Incorrect)
```python
return nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
    target_offset=target_offset,
    source_rotation_center=source_center,
    angle=angle,
    scale=scale)  # ❌ WRONG - parameter is called 'scalar' not 'scale'
```

## Fixed Code
```python
return nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
    target_offset=target_offset,
    source_rotation_center=source_center,
    angle=angle,
    scalar=scale)  # ✅ CORRECT - use 'scalar' parameter name
```

## How to Apply Fix

### Option 1: Patch the installed package
```bash
# Find the factory.py file
FACTORY_FILE=$(python3.13 -c "import nornir_imageregistration.transforms.factory as f; print(f.__file__)")

# Make a backup
cp "$FACTORY_FILE" "${FACTORY_FILE}.backup"

# Apply the fix (requires sed or manual editing)
sed -i 's/scale=scale)/scalar=scale)/g' "$FACTORY_FILE"
```

### Option 2: Submit PR to nornir_imageregistration
This fix should be submitted to the nornir_imageregistration repository at:
https://github.com/jamesra/nornir-imageregistration

### Option 3: Use Workaround
Until the fix is applied, use this workaround:
1. Save transforms as Mesh type instead of Rigid
2. Load the Mesh transform
3. Convert to Rigid after loading:
```python
from nornir_imageregistration import transforms, StosFile

# Load as mesh
stos = StosFile.Load("file.stos")
mesh_transform = transforms.LoadTransform(stos.Transform)

# Convert to rigid
rigid_transform = transforms.ConvertTransform(
    mesh_transform, 
    transforms.TransformType.RIGID,
    source_image_shape=(height, width)
)
```

## Impact
- **Severity**: Medium
- **Affected**: All users trying to save/load Rigid transforms in STOS files
- **Workaround Available**: Yes (see Option 3 above)

## Verification
After applying the fix, verify with:
```python
import nornir_imageregistration.transforms as t
import numpy as np

# Create a rigid transform
pp = np.array([[100,100,105,102],[200,100,205,103],[100,200,102,205]], dtype=np.float64)
tri = t.Triangulation(pp)
rigid = t.ConvertTransform(tri, t.TransformType.RIGID, source_image_shape=(1000,1000))

# Save and load
rigid_str = rigid.ToITKString()
loaded = t.LoadTransform(rigid_str)  # Should not raise TypeError

print("✓ Fix verified - Rigid transform loads successfully")
```

## Related Tests
This issue was discovered during comprehensive testing of Pyre QT menu functionality.
See `TEST_REPORT.md` for full test results.
