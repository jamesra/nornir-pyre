from typing import Callable, NamedTuple


class VertexAttribute(NamedTuple):
    """Describes attributes of a vertex in a shader program.  Used to bind vertex attributes to a VAO"""
    location: Callable[[], int]  # Function to get the location of the attribute in the shader
    name: str  # Variable name of the attribute in the shader
    num_elements: int  # Number of elements in the attribute, ex: 3 for a vec3 in the shader
    type: int  # type of the elements in the attribute ex: GL_FLOAT
    instanced: bool = False  # True if the attribute is instanced, that is each value in the array is run for each vertex (glVertexAtrtribDivisor)
