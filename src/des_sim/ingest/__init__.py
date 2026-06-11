from .aei import AnthropicEconomicIndex
from .ai_prices import AiPrices
from .btos import BTOS
from .design_demand import DesignDemand
from .hiring_lab import HiringLab
from .layoffs import LayoffsFyi
from .levels import LevelsFyi
from .oews import OEWS
from .onet import OnetTasks

SOURCES = {
    cls.name: cls
    for cls in (
        HiringLab,
        BTOS,
        OEWS,
        AnthropicEconomicIndex,
        LayoffsFyi,
        LevelsFyi,
        OnetTasks,
        DesignDemand,
        AiPrices,
    )
}
