from typing import Callable, Sequence

import numpy as np
from numpy.typing import NDArray

# Used to set the selection of control points or any other set of objects that can be selected
SetSelectionCallable = Callable[[Sequence[int] | NDArray[np.integer]], None]
