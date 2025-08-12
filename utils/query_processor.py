import re
import logging

logger = logging.getLogger(__name__)

class QueryProcessor:
    def process_search_query(self, query_param, season=None, episode=None):
        """Process search query with enhanced Sonarr support"""
        if not query_param:
            return "Spirited Away"
        
        query = query_param.strip()
        
        # Handle various formats that Sonarr might send
        if ' : ' in query:
            query = query.split(' : ')[0]
        
        # Remove season indicators from the title itself
        query = re.sub(r'\s+S\d+$', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+Season\s*\d+$', '', query, flags=re.IGNORECASE)
        
        # Remove year info like (2023)
        query = re.sub(r'\s*\(\d{4}\)$', '', query)
        
        # Remove episode patterns from title
        query = re.sub(r'\s+E\d+$', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+Episode\s*\d+$', '', query, flags=re.IGNORECASE)
        
        query = query.strip()
        
        logger.debug(f"Processed query: '{query}' (season={season}, episode={episode})")
        return query