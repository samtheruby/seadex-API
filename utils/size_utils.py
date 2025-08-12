import re
import logging

logger = logging.getLogger(__name__)

class SizeUtils:
    def size_to_bytes(self, size_str):
        """Parse size string like '1.23 GiB' into bytes"""
        m = re.match(r"([\d\.]+)\s*(GiB|MiB|KiB|TiB|B)", size_str, re.I)
        if m:
            num, unit = m.groups()
            num = float(num)
            unit = unit.lower()
            multipliers = {
                'b': 1,
                'kib': 1024,
                'mib': 1024**2,
                'gib': 1024**3,
                'tib': 1024**4
            }
            return int(num * multipliers.get(unit, 1))
        return 0