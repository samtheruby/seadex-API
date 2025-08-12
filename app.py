from flask import Flask, request, Response
import logging
from services.search_service import SearchService
from services.xml_service import XMLService
from utils.query_processor import QueryProcessor

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize services
search_service = SearchService()
xml_service = XMLService()
query_processor = QueryProcessor()

@app.route('/api')
def api():
    t = request.args.get('t', '').lower()
    logger.debug(f"API request: {request.args}")

    if t == 'caps':
        return Response(xml_service.build_caps_xml(), mimetype='application/xml')

    elif t == 'search':
        query_param = request.args.get('q', '')
        return_type = request.args.get('response', 'xml')
        
        processed_query = query_processor.process_search_query(query_param)
        logger.info(f"Processed search query: '{processed_query}' (original: '{query_param}')")
        
        anilist_id, anime_name, processed_torrents = search_service.perform_search(processed_query)
        
        if not anilist_id or not processed_torrents:
            if return_type == 'json':
                return Response('{"usenetReleases": [], "torrentReleases": []}', 
                              mimetype='application/json', status=404)
            else:
                return Response(xml_service.build_empty_rss("SeadexNab - No Results", 
                                              f"No results found for: {processed_query}"), 
                              mimetype='application/xml')
        
        if return_type == 'json':
            json_response = {
                "usenetReleases": [],
                "torrentReleases": [{"title": t.get("title", ""), "url": t.get("url", "")} for t in processed_torrents]
            }
            return Response(str(json_response), mimetype='application/json')
        else:
            xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents)
            return Response(xml, mimetype='application/xml')

    elif t == 'tvsearch':
        query_param = request.args.get('q', '')
        season = request.args.get('season')
        episode = request.args.get('ep')
        
        try:
            season = int(season) if season else None
        except ValueError:
            season = None
            
        try:
            episode = int(episode) if episode else None
        except ValueError:
            episode = None
        
        processed_query = query_processor.process_search_query(query_param, season, episode)
        logger.info(f"TV search for: '{processed_query}' (season={season}, episode={episode})")
        
        anilist_id, anime_name, processed_torrents = search_service.perform_search(processed_query, season, episode)
        
        if not anilist_id or not processed_torrents:
            return Response(xml_service.build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents, season, episode)
        return Response(xml, mimetype='application/xml')

    elif t == 'movie':
        query_param = request.args.get('q', '')
        processed_query = query_processor.process_search_query(query_param)
        logger.info(f"Movie search for: '{processed_query}'")
        
        anilist_id, anime_name, processed_torrents = search_service.perform_search(processed_query)
        
        if not anilist_id or not processed_torrents:
            return Response(xml_service.build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents)
        return Response(xml, mimetype='application/xml')

    else:
        logger.error(f"Invalid request type: {t}")
        return Response("Invalid request", status=400)

@app.route('/test')
def test():
    """Test endpoint to debug the search functionality"""
    q = request.args.get('q', 'Fate/stay night')
    season = request.args.get('season')
    episode = request.args.get('ep')
    
    try:
        season = int(season) if season else None
    except ValueError:
        season = None
        
    try:
        episode = int(episode) if episode else None
    except ValueError:
        episode = None
    
    logger.info(f"Test search for: {q} (season={season}, episode={episode})")
    
    processed_query = query_processor.process_search_query(q, season, episode)
    anilist_id, anime_name, processed_torrents = search_service.perform_search(processed_query, season, episode)
    
    if not anilist_id:
        return f"Could not find AniList ID for: {q}"
    
    result = f"Found {len(processed_torrents)} torrents for {anime_name} (ID: {anilist_id})<br>"
    result += f"Processed query: {processed_query}<br><br>"
    
    for i, torrent in enumerate(processed_torrents):
        result += f"Torrent {i+1}:<br>"
        result += f"  - Season Pack: {torrent['is_season_pack']}<br>"
        result += f"  - Seasons: {torrent['seasons']}<br>"
        result += f"  - Episodes: {torrent['episode_numbers']}<br>"
        result += f"  - Release Group: {torrent['release_group']}<br>"
        result += f"  - Size: {torrent['total_size'] / (1024**3):.2f} GB<br>"
        result += f"  - Files: {torrent['episode_count']}<br><br>"
    
    return result

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9009, debug=True)