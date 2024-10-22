from typing import Callable, Sequence
from numpy.typing import NDArray

# Used to set the selection of control points or any other set of objects that can be selected
SetSelectionCallable = Callable[[Sequence[int] | NDArray[int]], None]
