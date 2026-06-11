from .aei import AnthropicEconomicIndex
from .btos import BTOS
from .hiring_lab import HiringLab
from .layoffs import LayoffsFyi
from .levels import LevelsFyi
from .oews import OEWS
from .onet import OnetTasks

SOURCES = {
    cls.name: cls
    for cls in (HiringLab, BTOS, OEWS, AnthropicEconomicIndex, LayoffsFyi, LevelsFyi, OnetTasks)
}
