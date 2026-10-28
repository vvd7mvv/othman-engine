"""محرك عثمان: يتعرف على السورة والآيات في تلاوة، ويعطي وقت كل آية وكل كلمة ووقفات النفَس."""
from othman_engine.alignment import Alignment, Segment
from othman_engine.engine import Engine
from othman_engine.errors import ProcessingError

__all__ = ["Alignment", "Engine", "ProcessingError", "Segment"]
__version__ = "0.3.0"
