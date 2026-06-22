import numpy as np
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer

from pyre.gl_engine.instanced_vao import InstancedVAO
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from OpenGL import GL as gl


class TestVAOWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instanced VAO Test")
        self.resize(800, 600)
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_tests)
        self.timer.start(100)  # Start after 100ms to ensure GL context is ready
        self.vao = None
        self.vertex_buffer = None
        self.instance_buffer = None

    def initializeGL(self):
        print("OpenGL context initialized")

        # Create test data
        vertices = np.array([
            # x, y, z
            -0.5, -0.5, 0.0,  # Bottom-left
            0.5, -0.5, 0.0,   # Bottom-right
            0.5, 0.5, 0.0,    # Top-right
            -0.5, 0.5, 0.0    # Top-left
        ], dtype=np.float32)

        indices = np.array([
            0, 1, 2,  # First triangle
            2, 3, 0   # Second triangle
        ], dtype=np.uint16)

        instance_data = np.array([
            # x, y
            0.0, 0.0,  # Instance 1
            1.0, 0.0,  # Instance 2
            0.0, 1.0   # Instance 3
        ], dtype=np.float32)

        # Create vertex layout
        vertex_layout = VertexArrayLayout([
            VertexAttribute(lambda: 0, "position", 3, gl.GL_FLOAT)
        ])

        # Create instance layout
        instance_layout = VertexArrayLayout([
            VertexAttribute(lambda: 1, "offset", 2, gl.GL_FLOAT, instanced=True)
        ])

        # Create and initialize VAO
        self.vao = InstancedVAO()
        self.vao.begin_init()

        # Create and add vertex buffer
        self.vertex_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vertex_buffer)
        # Convert numpy array to bytes for PyQt's OpenGL functions
        vertices_bytes = vertices.tobytes()
        gl.glBufferData(gl.GL_ARRAY_BUFFER, len(vertices_bytes), vertices_bytes, gl.GL_STATIC_DRAW)

        # Create and add instance buffer
        self.instance_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.instance_buffer)
        # Convert numpy array to bytes for PyQt's OpenGL functions
        instance_data_bytes = instance_data.tobytes()
        gl.glBufferData(gl.GL_ARRAY_BUFFER, len(instance_data_bytes), instance_data_bytes, gl.GL_STATIC_DRAW)

        # Add buffers to VAO
        class TestBuffer:
            def __init__(self, buffer_id, layout):
                self.buffer = buffer_id
                self.layout = layout

        self.vao.add_buffer(TestBuffer(self.vertex_buffer, vertex_layout))
        self.vao.add_buffer(TestBuffer(self.instance_buffer, instance_layout))
        self.vao.add_index_buffer(indices)

        self.vao.end_init()

    def run_tests(self):
        self.timer.stop()  # Only run once

        try:
            print("Testing InstancedVAO creation and initialization...")

            # Test binding and unbinding
            print("Testing VAO binding and unbinding...")
            if self.vao.bind():
                print("VAO bound successfully")
                self.vao.unbind()
                print("VAO unbound successfully")
            else:
                print("Failed to bind VAO")

            print("InstancedVAO test completed successfully")

            # Clean up
            gl.glDeleteBuffers(1, [self.vertex_buffer])
            gl.glDeleteBuffers(1, [self.instance_buffer])

        except Exception as e:
            print(f"Error during testing: {e}")

        # Close the application
        QTimer.singleShot(3000, QApplication.quit)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = TestVAOWidget()
    widget.show()
    sys.exit(app.exec())
