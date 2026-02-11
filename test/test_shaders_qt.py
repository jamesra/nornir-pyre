import numpy as np
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer

# Import shader modules
from pyre.gl_engine.shaders import (
    TextureShaderQt, 
    ColorShaderQt, 
    TransformShaderQt, 
    PointSetShaderQt, 
    ControlPointSetShaderQt, 
    OverlayShaderQt,
    InitializeShadersQt
)


class TestShadersWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt Shaders Test")
        self.resize(800, 600)
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_tests)
        self.timer.start(100)  # Start after 100ms to ensure GL context is ready

    def initializeGL(self):
        print("OpenGL context initialized")

    def run_tests(self):
        self.timer.stop()  # Only run once

        try:
            print("Testing Qt-based shader initialization...")
            
            # Initialize all shaders
            print("Initializing all Qt-based shaders...")
            InitializeShadersQt()
            print("All Qt-based shaders initialized successfully")
            
            # Test individual shader classes
            print("\nTesting TextureShaderQt...")
            texture_shader = TextureShaderQt()
            texture_shader.initialize_gl_objects()
            print(f"TextureShaderQt initialized, program ID: {texture_shader.program.programId()}")
            
            print("\nTesting ColorShaderQt...")
            color_shader = ColorShaderQt()
            color_shader.initialize_gl_objects()
            print(f"ColorShaderQt initialized, program ID: {color_shader.program.programId()}")
            
            print("\nTesting TransformShaderQt...")
            transform_shader = TransformShaderQt()
            transform_shader.initialize_gl_objects()
            print(f"TransformShaderQt initialized, program ID: {transform_shader.program.programId()}")
            
            print("\nTesting PointSetShaderQt...")
            pointset_shader = PointSetShaderQt()
            pointset_shader.initialize_gl_objects()
            print(f"PointSetShaderQt initialized, program ID: {pointset_shader.program.programId()}")
            
            print("\nTesting ControlPointSetShaderQt...")
            controlpointset_shader = ControlPointSetShaderQt()
            controlpointset_shader.initialize_gl_objects()
            print(f"ControlPointSetShaderQt initialized, program ID: {controlpointset_shader.program.programId()}")
            
            print("\nTesting OverlayShaderQt...")
            overlay_shader = OverlayShaderQt()
            overlay_shader.initialize_gl_objects()
            print(f"OverlayShaderQt initialized, program ID: {overlay_shader.program.programId()}")
            
            # Test shader attribute and uniform locations
            print("\nTesting shader attribute and uniform locations...")
            
            # Test TextureShaderQt locations
            print("Testing TextureShaderQt locations...")
            source_pos = texture_shader.source_pos_location
            target_pos = texture_shader.target_pos_location
            texture_coord = texture_shader.texture_coord_location
            texture_loc = texture_shader.texture_location
            tween_loc = texture_shader.tween_location
            mvp_loc = texture_shader.model_view_projection_matrix_location
            print(f"TextureShaderQt locations: source_pos={source_pos}, target_pos={target_pos}, "
                  f"texture_coord={texture_coord}, texture={texture_loc}, tween={tween_loc}, mvp={mvp_loc}")
            
            # Test PointSetShaderQt locations
            print("Testing PointSetShaderQt locations...")
            vertex_loc = pointset_shader.vertex_location
            texture_coord = pointset_shader.texture_coord_location
            source_offset = pointset_shader.point_source_offset_location
            target_offset = pointset_shader.point_target_offset_location
            texture_sampler = pointset_shader.texture_sampler
            tween_loc = pointset_shader.tween_location
            mvp_loc = pointset_shader.model_view_projection_matrix_location
            print(f"PointSetShaderQt locations: vertex={vertex_loc}, texture_coord={texture_coord}, "
                  f"source_offset={source_offset}, target_offset={target_offset}, "
                  f"texture_sampler={texture_sampler}, tween={tween_loc}, mvp={mvp_loc}")
            
            print("\nAll Qt-based shader tests completed successfully")
            
        except Exception as e:
            print(f"Error during testing: {e}")
        
        # Close the application
        QTimer.singleShot(3000, QApplication.quit)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = TestShadersWidget()
    widget.show()
    sys.exit(app.exec())