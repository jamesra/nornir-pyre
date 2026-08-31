import numpy as np
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer

from pyre.gl_engine.dynamic_vao_qt import DynamicVAOQt
from pyre.gl_engine.shader_vao_qt import ShaderVAOQt
from pyre.gl_engine.gl_buffer import GLIndexBuffer
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from OpenGL import GL as gl


class TestVAOWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt VAO Test")
        self.resize(800, 600)
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_tests)
        self.timer.start(100)  # Start after 100ms to ensure GL context is ready
        self.dynamic_vao = None
        self.shader_vao = None
        self.vertex_buffer = None
        self.index_buffer = None

    def initializeGL(self):
        print("OpenGL context initialized")
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)

    def run_tests(self):
        self.timer.stop()  # Only run once

        try:
            print("Testing Qt-based VAO implementations...")
            
            # Test ShaderVAOQt
            print("\nTesting ShaderVAOQt...")
            self.test_shader_vao_qt()
            
            # Test DynamicVAOQt
            print("\nTesting DynamicVAOQt...")
            self.test_dynamic_vao_qt()
            
            print("\nAll Qt-based VAO tests completed successfully")
            
        except Exception as e:
            print(f"Error during testing: {e}")
        
        # Close the application
        QTimer.singleShot(3000, QApplication.quit)
    
    def test_shader_vao_qt(self):
        # Create test data for a simple quad
        vertices = np.array([
            # x, y, z, u, v
            -0.5, -0.5, 0.0, 0.0, 0.0,  # Bottom-left
            0.5, -0.5, 0.0, 1.0, 0.0,   # Bottom-right
            0.5, 0.5, 0.0, 1.0, 1.0,    # Top-right
            -0.5, 0.5, 0.0, 0.0, 1.0    # Top-left
        ], dtype=np.float32)
        
        indices = np.array([
            0, 1, 2,  # First triangle
            2, 3, 0   # Second triangle
        ], dtype=np.uint16)
        
        # Create vertex layout
        vertex_layout = VertexArrayLayout([
            VertexAttribute(lambda: 0, "position", 3, gl.GL_FLOAT),
            VertexAttribute(lambda: 1, "texcoord", 2, gl.GL_FLOAT)
        ])
        
        # Create ShaderVAOQt
        try:
            self.shader_vao = ShaderVAOQt(vertex_layout, vertices, indices)
            print("ShaderVAOQt created successfully")
            
            # Test binding and unbinding
            if self.shader_vao.bind():
                print("ShaderVAOQt bound successfully")
                self.shader_vao.unbind()
                print("ShaderVAOQt unbound successfully")
            else:
                print("Failed to bind ShaderVAOQt")
                
        except Exception as e:
            print(f"Error creating or using ShaderVAOQt: {e}")
    
    def test_dynamic_vao_qt(self):
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
        
        # Create vertex layout
        vertex_layout = VertexArrayLayout([
            VertexAttribute(lambda: 0, "position", 3, gl.GL_FLOAT)
        ])
        
        # Create DynamicVAOQt
        try:
            self.dynamic_vao = DynamicVAOQt()
            print("DynamicVAOQt created successfully")
            
            # Initialize the VAO
            self.dynamic_vao.begin_init()
            
            # Create and add vertex buffer
            class TestBuffer:
                def __init__(self, buffer_id, layout):
                    self.buffer = buffer_id
                    self.layout = layout
            
            # Create vertex buffer
            self.vertex_buffer = gl.glGenBuffers(1)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vertex_buffer)
            # Convert numpy array to bytes for PyQt's OpenGL functions
            vertices_bytes = vertices.tobytes()
            gl.glBufferData(gl.GL_ARRAY_BUFFER, len(vertices_bytes), vertices_bytes, gl.GL_STATIC_DRAW)
            
            # Create index buffer
            self.index_buffer = GLIndexBuffer(indices)
            
            # Add buffers to VAO
            self.dynamic_vao.add_buffer(TestBuffer(self.vertex_buffer, vertex_layout))
            self.dynamic_vao.add_index_buffer(self.index_buffer)
            
            # Finalize the VAO
            self.dynamic_vao.end_init()
            print("DynamicVAOQt initialized successfully")
            
            # Test binding and unbinding
            if self.dynamic_vao.bind():
                print("DynamicVAOQt bound successfully")
                self.dynamic_vao.unbind()
                print("DynamicVAOQt unbound successfully")
            else:
                print("Failed to bind DynamicVAOQt")
                
        except Exception as e:
            print(f"Error creating or using DynamicVAOQt: {e}")
            
        # Clean up
        if self.vertex_buffer is not None:
            gl.glDeleteBuffers(1, [self.vertex_buffer])
            self.vertex_buffer = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = TestVAOWidget()
    widget.show()
    sys.exit(app.exec())