from typing import Sequence

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error
from pyre.gl_engine.instanced_vao import InstancedVAO
from pyre.gl_engine.shaders.shader_base import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_controlpointset_vertex_shader_program = """
        #version 450
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 view_projection_matrix;
        uniform float scale; //The scale of the points
        out vec2 frag_texture_coordinate;
        in vec3 vertex_position; // Verticies for a square centered at the origin 
        in vec2 vertex_texture_coordinate;
        in vec2 point_source_offset; //The position of the point in source space
        in vec2 point_target_offset; //The position of the point in target space
        in float texture_index; // 0 idle, 1 selected, 2 busy
        out float frag_texture_index;
        const float BUSY_QUAD_SCALE = 2.0;
        
        mat4 BuildTranslation(vec3 delta)
        {
            return mat4(
                vec4(1.0, 0.0, 0.0, 0.0),
                vec4(0.0, 1.0, 0.0, 0.0),
                vec4(0.0, 0.0, 1.0, 0.0),
                vec4(delta, 1.0));
        }
        
        mat4 BuildScaleTranslation(float scale, vec3 delta)
        {
            return mat4(
                vec4(scale, 0.0, 0.0, 0.0),
                vec4(0.0, scale, 0.0, 0.0),
                vec4(0.0, 0.0, 1.0, 0.0),
                vec4(delta, 1.0));
        }

        void main(){ 
            vec3 blended_offset_pos = mix(vec3(point_source_offset, 1),
                                   vec3(point_target_offset, 1),
                                   tween);
            vec3 local_vertex = vertex_position;
            if (texture_index >= 1.5) {
                local_vertex = vertex_position * BUSY_QUAD_SCALE;
            }
            mat4 translate_matrix;
            translate_matrix = BuildScaleTranslation(scale, blended_offset_pos);
            mat4 model_view_proj;
            model_view_proj =  view_projection_matrix * translate_matrix; 
            gl_Position = model_view_proj * vec4(local_vertex, 1.0);
            frag_texture_coordinate = vertex_texture_coordinate;
            frag_texture_index = texture_index;
        }
"""

_controlpointset_fragment_shader_program = """
    #version 450
    uniform sampler2DArray texture_sampler;
    uniform float busy_angle; // Spin angle for the busy comet, radians
    in vec2 frag_texture_coordinate;
    in float frag_texture_index;
    out vec4 outputColor;
    const float BUSY_QUAD_SCALE = 2.0;
    const float PI = 3.14159265359;
    const float COMET_ARC = 1.0 / 3.0;
    const float COMET_STROKE = 0.18;
    const vec3 GLYPH_GREY = vec3(0.78);
    const vec3 COMET_BLUE = vec3(0.35, 0.65, 1.0);

    void main() {
        if (frag_texture_index < 1.5) {
            outputColor = texture(
                texture_sampler, vec3(frag_texture_coordinate, frag_texture_index)
            );
            return;
        }

        vec2 glyphUV = 0.5 + (frag_texture_coordinate - 0.5) * BUSY_QUAD_SCALE;
        vec4 texColor = vec4(0.0);
        if (glyphUV.x >= 0.0 && glyphUV.x <= 1.0 && glyphUV.y >= 0.0 && glyphUV.y <= 1.0) {
            texColor = texture(texture_sampler, vec3(glyphUV, 0.0));
        }
        vec4 glyph = vec4(GLYPH_GREY, texColor.a);

        vec2 p = frag_texture_coordinate * 2.0 - 1.0;
        float r = length(p);
        float ang = atan(p.y, p.x);
        float a = fract((ang - busy_angle) / (2.0 * PI));
        float along = clamp(a / COMET_ARC, 0.0, 1.0);
        float arcMask = 1.0 - smoothstep(COMET_ARC - 0.02, COMET_ARC + 0.02, a);
        // Keep the whole 1/3-turn readable; pow(1-t,2) plus SRC_ALPHA made only the head a spec.
        float tail = 1.0 - along;
        float cometAlong = mix(0.5, 1.0, pow(tail, 0.6)) * arcMask;
        float rGlyph = 1.0 / BUSY_QUAD_SCALE;
        float rInner = rGlyph + 0.03;
        float rOuter = rInner + COMET_STROKE;
        float ring = smoothstep(rInner - 0.02, rInner + 0.02, r)
            * (1.0 - smoothstep(rOuter - 0.02, rOuter + 0.02, r));
        float cometAlpha = cometAlong * ring;
        vec4 comet = vec4(COMET_BLUE, cometAlpha);

        float outA = glyph.a + comet.a * (1.0 - glyph.a);
        vec3 premul = glyph.rgb * glyph.a + comet.rgb * comet.a * (1.0 - glyph.a);
        outputColor = vec4(outA > 0.0 ? premul / outA : vec3(0.0), outA);
    }
"""


class ControlPointSetShader(BaseShader):
    """Instanced control-point billboards.

    Instance ``texture_index`` 0/1 sample the idle/selected texture layers.
    Index 2 is busy: the glyph stays upright and light-grey while a blue comet
    arc spins in the extra margin outside the point.
    """

    _texture_sampler_location: int | None = None

    _vertex_location: int | None = None
    _vertex_texture_location: int | None = None
    _point_source_offset_location: int | None = None
    _point_target_offset_location: int | None = None
    _tween_location: int | None = None
    _scale_location: int | None = None
    _view_projection_matrix_location: int | None = None
    _busy_angle_location: int | None = None
    _attributes: Sequence[VertexAttribute] | None = None
    _vertex_layout: VertexArrayLayout | None = None
    _pointset_layout: VertexArrayLayout | None = None
    _texture_index_location: int | None = None  # Index of the texture the instance should use

    @property
    def vertex_layout(self) -> VertexArrayLayout | None:
        """The layout of the vertex buffer"""
        return self._vertex_layout

    @property
    def pointset_layout(self) -> VertexArrayLayout | None:
        """
        The layout for the pointset buffer.
        SourceX, SourceY, TargetX, TargetY for each point
        """
        return self._pointset_layout

    @property
    def texture_index_layout(self) -> VertexArrayLayout:
        """
        The layout for the texture index buffer.
        """
        return self._texture_index_layout

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _pointset_vertex_shader_program
        global _pointset_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.vertex_location, "vertex_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._pointset_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.point_target_offset_location, "point_target_offset", 2, gl.GL_FLOAT,
                             instanced=True),
             VertexAttribute(lambda: self.point_source_offset_location, "point_source_offset", 2, gl.GL_FLOAT,
                             instanced=True),
             ])

        self._texture_index_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.texture_index_location, "texture_index", 1, gl.GL_FLOAT,
                             instanced=True)])

        self._vertex_shader = VertexShader(_controlpointset_vertex_shader_program)

        self._fragment_shader = FragmentShader(_controlpointset_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def texture_index_location(self) -> int:
        if self._texture_index_location is None:
            self._texture_index_location = gl.glGetAttribLocation(self.program, "texture_index")
            if self._texture_index_location == -1:
                raise ValueError("Could not find attribute")
        assert self._texture_index_location is not None
        return self._texture_index_location

    @property
    def vertex_location(self) -> int:
        if self._vertex_location is None:
            self._vertex_location = gl.glGetAttribLocation(self.program, "vertex_position")
            if self._vertex_location == -1:
                raise ValueError("Could not find attribute")
        assert self._vertex_location is not None
        return self._vertex_location

    @property
    def texture_coord_location(self) -> int:
        if self._vertex_texture_location is None:
            self._vertex_texture_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._vertex_texture_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        assert self._vertex_texture_location is not None
        return self._vertex_texture_location

    @property
    def point_source_offset_location(self) -> int:
        if self._point_source_offset_location is None:
            self._point_source_offset_location = gl.glGetAttribLocation(self.program, "point_source_offset")
            if self._point_source_offset_location == -1:
                raise ValueError("Could not find attribute")
        assert self._point_source_offset_location is not None
        return self._point_source_offset_location

    @property
    def point_target_offset_location(self) -> int:
        if self._point_target_offset_location is None:
            self._point_target_offset_location = gl.glGetAttribLocation(self.program, "point_target_offset")
            if self._point_target_offset_location == -1:
                raise ValueError("Could not find attribute")
        assert self._point_target_offset_location is not None
        return self._point_target_offset_location

    @property
    def texture_sampler(self):
        if self._texture_sampler_location is None:
            self._texture_sampler_location = gl.glGetUniformLocation(self.program, "texture_sampler")
            if self._texture_sampler_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_sampler_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        assert self._tween_location is not None
        return self._tween_location

    @property
    def scale_location(self) -> int:
        if self._scale_location is None:
            self._scale_location = gl.glGetUniformLocation(self.program, "scale")
            if self._scale_location == -1:
                raise ValueError("Could not find attribute")
        assert self._scale_location is not None
        return self._scale_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._view_projection_matrix_location is None:
            self._view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                            "view_projection_matrix")
            if self._view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        assert self._view_projection_matrix_location is not None
        return self._view_projection_matrix_location

    @property
    def busy_angle_location(self) -> int:
        if self._busy_angle_location is None:
            self._busy_angle_location = gl.glGetUniformLocation(self.program, "busy_angle")
            if self._busy_angle_location == -1:
                raise ValueError("Could not find busy_angle uniform")
        assert self._busy_angle_location is not None
        return self._busy_angle_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating],
             texture: int,
             vao: InstancedVAO,
             num_instances: int,
             scale: float,
             tween: float,
             busy_angle: float = 0.0):
        """Draw instanced control-point billboards.

        ``busy_angle`` drives the comet arc for instances with texture index 2.
        """
        if num_instances == 0:
            return

        try:
            gl.glUseProgram(self.program)
            check_for_error()
            if not vao.bind():
                return  # Skip drawing if the vao isn't able to bind (May be invalid)

            gl.glActiveTexture(gl.GL_TEXTURE0)
            check_for_error()
            gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, texture)
            check_for_error()
            gl.glUniform1i(self.texture_sampler, 0)
            check_for_error()

            gl.glUniform1f(self.tween_location, tween)
            check_for_error()
            gl.glUniform1f(self.scale_location, scale)
            check_for_error()
            gl.glUniform1f(self.busy_angle_location, float(busy_angle))
            check_for_error()
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32))
            check_for_error()

            # status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            # if status != gl.GL_FRAMEBUFFER_COMPLETE:
            #    print("Framebuffer is not complete")
            gl.glDrawElementsInstanced(gl.GL_TRIANGLES, vao.num_elements,
                                       gl.GL_UNSIGNED_SHORT,
                                       None, num_instances)
            check_for_error()
        finally:
            check_for_error()
            vao.unbind()
            gl.glUseProgram(0)
            check_for_error("after glUseProgram(0) in controlpointset_shader draw")
