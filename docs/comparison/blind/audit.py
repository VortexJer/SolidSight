# Neutral audit of the blind one-shot output: import its STL and let the
# validator + renderer judge it with the same criteria as any other part.
from solidsight import *

emit(from_stl("engine_blind.stl"), name="blind_block", color="gray")
