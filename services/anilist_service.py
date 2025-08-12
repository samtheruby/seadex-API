import requests
import logging

logger = logging.getLogger(__name__)

class AniListService:
    def __init__(self):
        self.base_url = "https://graphql.anilist.co"

    def get_anilist_id_with_relations(self, anime_name, search_type="ANIME"):
        """Get AniList ID, related media, and year with enhanced movie support"""
        logger.debug(f"Searching AniList for: {anime_name} (type: {search_type})")
        
        query = '''
        query ($search: String, $type: MediaType) {
          Page(page: 1, perPage: 15) {
            media(search: $search, type: $type, sort: [POPULARITY_DESC, START_DATE_DESC]) {
              id
              title {
                romaji
                english
                native
              }
              startDate {
                year
                month
                day
              }
              endDate {
                year
              }
              popularity
              format
              status
              episodes
              duration
              genres
              relations {
                edges {
                  relationType
                  node {
                    id
                    title {
                      romaji
                      english
                      native
                    }
                    format
                    startDate {
                      year
                    }
                    episodes
                    duration
                  }
                }
              }
            }
          }
        }
        '''
        variables = {'search': anime_name, 'type': search_type}
        
        try:
            res = requests.post(self.base_url, json={'query': query, 'variables': variables})
            res.raise_for_status()
            data = res.json()
            logger.debug(f"AniList response: {data}")
            
            media_list = data.get("data", {}).get("Page", {}).get("media", [])
            if not media_list:
                logger.debug("No anime found in AniList")
                return None, None, [], None, None
            
            # Smart selection logic for movies vs series
            main_anime = None
            
            # Special handling for well-known movies
            if anime_name.lower() in ["akira", "spirited away", "your name", "weathering with you"]:
                # Prefer movies for these titles
                for media in media_list:
                    if media.get("format") == "MOVIE":
                        main_anime = media
                        break
            
            # For movie searches, prefer MOVIE format
            if search_type == "ANIME" and not main_anime:
                for media in media_list:
                    if media.get("format") == "MOVIE":
                        main_anime = media
                        break
            
            # Fallback to first result
            if not main_anime:
                main_anime = media_list[0]
            
            # Collect related media based on type
            all_related_ids = [main_anime["id"]]
            main_title = main_anime["title"]["romaji"]
            main_format = main_anime.get("format", "")
            main_year = main_anime.get("startDate", {}).get("year")
            
            logger.debug(f"Main anime format: {main_format}, year: {main_year}")
            
            # Get relations - different logic for movies vs series
            relations = main_anime.get("relations", {}).get("edges", [])
            for relation in relations:
                relation_type = relation.get("relationType", "")
                related_media = relation.get("node", {})
                related_format = related_media.get("format", "")
                
                if main_format == "MOVIE":
                    # For movies, include sequels, prequels, and related movies
                    if relation_type in ["SEQUEL", "PREQUEL", "SIDE_STORY", "ALTERNATIVE"] and related_format == "MOVIE":
                        related_id = related_media.get("id")
                        if related_id and related_id not in all_related_ids:
                            all_related_ids.append(related_id)
                            related_title = related_media.get("title", {}).get("romaji", "")
                            logger.debug(f"Found related movie: {related_title} (ID: {related_id}, Type: {relation_type})")
                else:
                    # For series, use existing logic
                    if relation_type in ["SEQUEL", "PREQUEL"]:
                        if related_format in ["TV", "MOVIE"]:
                            related_id = related_media.get("id")
                            if related_id and related_id not in all_related_ids:
                                all_related_ids.append(related_id)
                                related_title = related_media.get("title", {}).get("romaji", "")
                                logger.debug(f"Found related season: {related_title} (ID: {related_id}, Type: {relation_type})")
            
            logger.debug(f"Found main anime: {main_title} ({main_format}) with {len(all_related_ids)} total entries")
            return main_anime["id"], main_title, all_related_ids, main_format, main_year
            
        except Exception as e:
            logger.error(f"Error querying AniList: {e}")
            return None, None, [], None, None
