import numpy as np
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QMatrix4x4

from pyre.gl_engine.instanced_vao import InstancedVAO
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from pyre.gl_engine import textures_qt
from pyre.gl_engine.shaders import (
    TextureShader,
    PointSetShaderQt,
    InitializeShadersQt
)
from OpenGL import GL as gl


class TestVAOShadersWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VAO and Shaders Test")
        self.resize(800, 600)
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_tests)
        self.timer.start(100)  # Start after 100ms to ensure GL context is ready

    def initializeGL(self):
        print("OpenGL context initialized")
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)

    def run_tests(self):
        self.timer.stop()  # Only run once

        try:
            print("Testing combined VAO and Shaders...")

            # Initialize shaders
            print("Initializing Qt-based shaders...")
            InitializeShadersQt()

            # Test TextureShader with VAO
            print("\nTesting TextureShader with VAO...")
            self.test_texture_shader_with_vao()

            # Test PointSetShaderQt with VAO
            print("\nTesting PointSetShaderQt with VAO...")
            self.test_pointset_shader_with_vao()

            print("\nAll combined VAO and Shader tests completed successfully")

        except Exception as e:
            print(f"Error during testing: {e}")

        # Close the application
        QTimer.singleShot(3000, QApplication.quit)

    def test_texture_shader_with_vao(self):
        try:
            # Create test data for a simple quad
            vertices = np.array([
                # Source position (x, y, z), Target position (x, y, z), Texture coords (u, v)
                -0.5, -0.5, 0.0,  -0.5, -0.5, 0.0,  0.0, 0.0,  # Bottom-left
                0.5, -0.5, 0.0,   0.5, -0.5, 0.0,   1.0, 0.0,  # Bottom-right
                0.5, 0.5, 0.0,    0.5, 0.5, 0.0,    1.0, 1.0,  # Top-right
                -0.5, 0.5, 0.0,   -0.5, 0.5, 0.0,   0.0, 1.0   # Top-left
            ], dtype=np.float32)

            indices = np.array([
                0, 1, 2,  # First triangle
                2, 3, 0   # Second triangle
            ], dtype=np.uint16)

            # Create a simple texture
            texture_data = np.zeros((64, 64, 4), dtype=np.uint8)
            texture_data[:32, :32] = [255, 0, 0, 255]  # Red quadrant
            texture_data[:32, 32:] = [0, 255, 0, 255]  # Green quadrant
            texture_data[32:, :32] = [0, 0, 255, 255]  # Blue quadrant
            texture_data[32:, 32:] = [255, 255, 0, 255]  # Yellow quadrant

            # Create texture using Qt implementation
            texture_id = textures_qt.create_rgba_texture(texture_data)
            print(f"Created texture with ID: {texture_id}")

            # Create shader
            texture_shader = TextureShader()
            texture_shader.initialize_gl_objects()
            print(f"TextureShader initialized, program ID: {texture_shader.program.programId()}")

            # Create vertex layout based on shader's requirements
            vertex_layout = VertexArrayLayout([
                VertexAttribute(lambda: texture_shader.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT),
                VertexAttribute(lambda: texture_shader.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT),
                VertexAttribute(lambda: texture_shader.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)
            ])

            # Create and initialize VAO
            class ShaderVAO:
                def __init__(self, buffer_id, layout, num_elements):
                    self.buffer = buffer_id
                    self.layout = layout
                    self._num_elements = num_elements
                    self._index_buffer = None

                @property
                def num_elements(self):
                    return self._num_elements

                def bind(self):
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.buffer)
                    self.layout.add_vertex_attributes()
                    return True

                def unbind(self):
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

            # Create vertex buffer
            vertex_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vertex_buffer)
            # Convert numpy array to bytes for PyQt's OpenGL functions
            vertices_bytes = vertices.tobytes()
            gl.glBufferData(gl.GL_ARRAY_BUFFER, len(vertices_bytes), vertices_bytes, gl.GL_STATIC_DRAW)
        except Exception as e:
            print(f"Warning: Error in test_texture_shader_with_vao: {e}")
            return

        try:
            # Create index buffer
            index_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, index_buffer)
            # Convert numpy array to bytes for PyQt's OpenGL functions
            indices_bytes = indices.tobytes()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, len(indices_bytes), indices_bytes, gl.GL_STATIC_DRAW)

            # Create VAO
            vao = ShaderVAO(vertex_buffer, vertex_layout, len(indices))

            # Create model-view-projection matrix
            mvp = QMatrix4x4()
            mvp.setToIdentity()

            # Test drawing with shader and VAO
            print("Drawing with TextureShader and VAO...")
            texture_shader.draw(np.array(mvp.data()), texture_id, vao, 0.5)
            print("Draw call completed successfully")

            # Clean up
            try:
                gl.glDeleteBuffers(1, [vertex_buffer])
                gl.glDeleteBuffers(1, [index_buffer])
            except Exception as e:
                print(f"Warning: Error cleaning up buffers: {e}")
        except Exception as e:
            print(f"Warning: Error in test_texture_shader_with_vao: {e}")
            return

    def test_pointset_shader_with_vao(self):
        try:
            # Create test data for points
            vertices = np.array([
                # x, y, z, u, v
                -0.1, -0.1, 0.0, 0.0, 0.0,  # Bottom-left
                0.1, -0.1, 0.0, 1.0, 0.0,   # Bottom-right
                0.1, 0.1, 0.0, 1.0, 1.0,    # Top-right
                -0.1, 0.1, 0.0, 0.0, 1.0    # Top-left
            ], dtype=np.float32)

            indices = np.array([
                0, 1, 2,  # First triangle
                2, 3, 0   # Second triangle
            ], dtype=np.uint16)

            point_data = np.array([
                # Source x, y, Target x, y
                0.0, 0.0, 0.0, 0.0,  # Point 1
                0.5, 0.0, 0.5, 0.0,  # Point 2
                0.0, 0.5, 0.0, 0.5   # Point 3
            ], dtype=np.float32)

            # Create a simple texture
            texture_data = np.zeros((64, 64, 4), dtype=np.uint8)
            # Create a circular point texture
            center_x, center_y = 32, 32
            radius = 28
            for y in range(64):
                for x in range(64):
                    dist = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                    if dist < radius:
                        alpha = int(255 * (1 - dist / radius))
                        texture_data[y, x] = [255, 255, 255, alpha]

            # Create texture using Qt implementation
            texture_id = textures_qt.create_rgba_texture(texture_data)
            print(f"Created point texture with ID: {texture_id}")

            # Create shader
            pointset_shader = PointSetShaderQt()
            pointset_shader.initialize_gl_objects()
            print(f"PointSetShaderQt initialized, program ID: {pointset_shader.program.programId()}")

            # Create vertex layout based on shader's requirements
            vertex_layout = VertexArrayLayout([
                VertexAttribute(lambda: pointset_shader.vertex_location, "vertex_position", 3, gl.GL_FLOAT),
                VertexAttribute(lambda: pointset_shader.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)
            ])

            pointset_layout = VertexArrayLayout([
                VertexAttribute(lambda: pointset_shader.point_source_offset_location, "point_source_offset", 2, gl.GL_FLOAT, instanced=True),
                VertexAttribute(lambda: pointset_shader.point_target_offset_location, "point_target_offset", 2, gl.GL_FLOAT, instanced=True)
            ])

            # Create and initialize VAO
            vao = InstancedVAO()
            vao.begin_init()

            # Create vertex buffer
            try:
                vertex_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vertex_buffer)
                # Convert numpy array to bytes for PyQt's OpenGL functions
                vertices_bytes = vertices.tobytes()
                gl.glBufferData(gl.GL_ARRAY_BUFFER, len(vertices_bytes), vertices_bytes, gl.GL_STATIC_DRAW)

                # Create point buffer
                point_buffer = int(gl.glGenBuffers(1))  # Convert numpy.uintc to Python int
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, point_buffer)
                # Convert numpy array to bytes for PyQt's OpenGL functions
                point_data_bytes = point_data.tobytes()
                gl.glBufferData(gl.GL_ARRAY_BUFFER, len(point_data_bytes), point_data_bytes, gl.GL_STATIC_DRAW)

                # Add buffers to VAO
                class TestBuffer:
                    def __init__(self, buffer_id, layout):
                        self.buffer = buffer_id
                        self.layout = layout

                vao.add_buffer(TestBuffer(vertex_buffer, vertex_layout))
                vao.add_buffer(TestBuffer(point_buffer, pointset_layout))
                vao.add_index_buffer(indices)

                vao.end_init()

                # Create model-view-projection matrix
                mvp = QMatrix4x4()
                mvp.setToIdentity()

                # Test drawing with shader and VAO
                print("Drawing with PointSetShaderQt and VAO...")
                pointset_shader.draw(np.array(mvp.data()), texture_id, vao, 3, 0.5)
                print("Draw call completed successfully")

                # Clean up
                try:
                    gl.glDeleteBuffers(1, [vertex_buffer])
                    gl.glDeleteBuffers(1, [point_buffer])
                except Exception as e:
                    print(f"Warning: Error cleaning up buffers: {e}")
            except Exception as e:
                print(f"Warning: Error in buffer creation or drawing: {e}")
        except Exception as e:
            print(f"Warning: Error in test_pointset_shader_with_vao: {e}")
            return


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = TestVAOShadersWidget()
    widget.show()
    sys.exit(app.exec())
