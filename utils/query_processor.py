import re
import logging

logger = logging.getLogger(__name__)

class QueryProcessor:
    def process_search_query(self, query_param, season=None, episode=None):
        """Process search query with enhanced Sonarr support and better movie handling"""
        if not query_param:
            return "Spirited Away"  # Default fallback
        
        query = str(query_param).strip()  # Ensure it's a string
        original_query = query
        
        # Handle various formats that Sonarr might send
        if ' : ' in query:
            query = query.split(' : ')[0]
        
        # Remove year info like (2023) or 2021 at the end - but store it for fallback
        year_match = re.search(r'(\d{4})', query)
        extracted_year = year_match.group(1) if year_match else None
        
        # Remove year from query
        query = re.sub(r'\s*\(\d{4}\)$', '', query)
        query = re.sub(r'\s+\d{4}$', '', query)
        
        # Remove season indicators from the title itself
        query = re.sub(r'\s+S\d+$', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+Season\s*\d+$', '', query, flags=re.IGNORECASE)
        
        # Remove episode patterns from title
        query = re.sub(r'\s+E\d+$', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+Episode\s*\d+$', '', query, flags=re.IGNORECASE)
        
        query = query.strip()
        
        # Special handling for movie titles with numbers (like "Jujutsu Kaisen 0")
        movie_indicators = ['0', 'movie', 'film', 'gekijo', 'gekijou', 'gekijouban']
        looks_like_movie = any(indicator in query.lower() for indicator in movie_indicators)
        
        # Ensure we always return a non-empty string
        if not query:
            query = "Spirited Away"
        
        logger.debug(f"Processed query: '{query}' (original: '{original_query}', year: {extracted_year}, looks_like_movie: {looks_like_movie})")
        return query
