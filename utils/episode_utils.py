import re
import logging

logger = logging.getLogger(__name__)

class EpisodeUtils:
    def extract_episode_info(self, filename):
        """Extract season and episode info from filename"""
        # Common patterns for episode numbering
        patterns = [
            r'S(\d+)E(\d+)',  # S01E01
            r'Season\s*(\d+).*?E(\d+)',  # Season 1 E01
            r'(\d+)x(\d+)',  # 1x01
            r'S(\d+).*?(\d+)',  # S01 01 (less reliable)
            r'E(\d+)',  # Just E01 (episode only)
            r'Episode\s*(\d+)',  # Episode 01
            r'Ep\.?\s*(\d+)',  # Ep. 01 or Ep 01
            r'(\d+)',  # Just a number (least reliable)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    # Season and episode
                    return int(groups[0]), int(groups[1])
                elif len(groups) == 1:
                    # Episode only
                    return None, int(groups[0])
        
        return None, None