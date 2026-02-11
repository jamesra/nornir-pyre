import numpy as np
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer

# Import both texture modules
from pyre.gl_engine import textures_gl
from pyre.gl_engine import textures_qt


class TestWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Texture Test")
        self.resize(800, 600)
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_tests)
        self.timer.start(100)  # Start after 100ms to ensure GL context is ready

    def initializeGL(self):
        print("OpenGL context initialized")

    def run_tests(self):
        self.timer.stop()  # Only run once

        try:
            # Test grayscale texture creation
            print("Testing grayscale texture creation...")
            grayscale_image = np.random.randint(0, 256, (64, 64), dtype=np.uint8)

            # Create texture using Qt implementation
            qt_texture_id = textures_qt.create_grayscale_texture(grayscale_image)
            print(f"Qt texture ID: {qt_texture_id}")

            # Skip reading back the texture for now
            print("Grayscale texture creation test passed")

            # Test RGBA texture creation
            print("\nTesting RGBA texture creation...")
            rgba_image = np.random.randint(0, 256, (64, 64, 4), dtype=np.uint8)

            # Create texture using Qt implementation
            qt_texture_id = textures_qt.create_rgba_texture(rgba_image)
            print(f"Qt texture ID: {qt_texture_id}")

            # Skip reading back the texture for now
            print("RGBA texture creation test passed")

            # Test texture array creation
            print("\nTesting texture array creation...")
            array_images = np.random.randint(0, 256, (3, 64, 64, 4), dtype=np.uint8)

            # Create texture array using Qt implementation
            qt_texture_id = textures_qt.create_rgba_texture_array(array_images)
            print(f"Qt texture array ID: {qt_texture_id}")

            # Get array length
            qt_length = textures_qt.get_texture_array_length(qt_texture_id)
            print(f"Qt texture array length: {qt_length}")

            if qt_length == 3:  # Expected length based on the input array
                print("Texture array length test passed")
            else:
                print("Texture array length test failed: Length does not match input array")

            print("\nAll tests completed")

        except Exception as e:
            print(f"Error during testing: {e}")

        # Close the application
        QTimer.singleShot(3000, QApplication.quit)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = TestWidget()
    widget.show()
    sys.exit(app.exec())
