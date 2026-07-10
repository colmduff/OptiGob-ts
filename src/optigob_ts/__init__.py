# read version from installed package
from importlib.metadata import version
__version__ = version("optigob-ts")

from optigob_ts.optigob import Optigob
from optigob_ts.common.logger import configure_logging, get_logger
