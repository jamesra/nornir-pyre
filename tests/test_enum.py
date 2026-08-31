from PyQt6.QtOpenGL import QOpenGLTexture

# Print available enum values
print("QOpenGLTexture.SwizzleComponent values:")
for name in dir(QOpenGLTexture.SwizzleComponent):
    if not name.startswith('_'):
        print(f"  {name}")