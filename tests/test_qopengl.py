from PyQt6.QtOpenGL import QOpenGLTexture
from PyQt6.QtWidgets import QApplication
import sys

# Print available methods for QOpenGLTexture
print("QOpenGLTexture methods:")
for name in dir(QOpenGLTexture):
    if not name.startswith('_'):
        print(f"  {name}")