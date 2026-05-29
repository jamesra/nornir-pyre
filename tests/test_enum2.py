from PyQt6.QtOpenGL import QOpenGLTexture

# Print available enum values for SwizzleValue
print("QOpenGLTexture.SwizzleValue values:")
for name in dir(QOpenGLTexture.SwizzleValue):
    if not name.startswith('_'):
        print(f"  {name}")