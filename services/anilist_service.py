import requests
import logging

logger = logging.getLogger(__name__)

class AniListService:
    def __init__(self):
        self.base_url = "https://graphql.anilist.co"

    def get_anilist_id_with_relations(self, anime_name):
        """Get AniList ID and all related media (seasons only, no OVAs/ONAs/etc.)"""
        logger.debug(f"Searching AniList for: {anime_name}")
        
        # First get the main anime
        query = '''
        query ($search: String) {
          Page(page: 1, perPage: 10) {
            media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
              id
              title {
                romaji
                english
                native
              }
              startDate {
                year
              }
              popularity
              format
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
                  }
                }
              }
            }
          }
        }
        '''
        variables = {'search': anime_name}
        
        try:
            res = requests.post(self.base_url, json={'query': query, 'variables': variables})
            res.raise_for_status()
            data = res.json()
            logger.debug(f"AniList response: {data}")
            
            media_list = data.get("data", {}).get("Page", {}).get("media", [])
            if not media_list:
                logger.debug("No anime found in AniList")
                return None, None, []
            
            # For "Akira" specifically, prefer the 1988 movie
            main_anime = None
            if anime_name.lower() == "akira":
                for media in media_list:
                    start_year = media.get("startDate", {}).get("year")
                    if start_year and start_year == 1988:
                        main_anime = media
                        break
            
            if not main_anime:
                main_anime = media_list[0]
            
            # Collect all related media (SEASONS ONLY)
            all_related_ids = [main_anime["id"]]
            main_title = main_anime["title"]["romaji"]
            
            # Get relations
            relations = main_anime.get("relations", {}).get("edges", [])
            for relation in relations:
                relation_type = relation.get("relationType", "")
                related_media = relation.get("node", {})
                
                # Only include sequels and prequels (main seasons)
                if relation_type in ["SEQUEL", "PREQUEL"]:
                    related_format = related_media.get("format", "")
                    # Only include TV series and movies (no OVAs, ONAs, specials)
                    if related_format in ["TV", "MOVIE"]:
                        related_id = related_media.get("id")
                        if related_id and related_id not in all_related_ids:
                            all_related_ids.append(related_id)
                            related_title = related_media.get("title", {}).get("romaji", "")
                            logger.debug(f"Found related season: {related_title} (ID: {related_id}, Type: {relation_type})")
            
            logger.debug(f"Found main anime: {main_title} with {len(all_related_ids)} total entries (seasons only)")
            return main_anime["id"], main_title, all_related_ids
            
        except Exception as e:
            logger.error(f"Error querying AniList: {e}")
            return None, None, []