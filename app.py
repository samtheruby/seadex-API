from flask import Flask, request, Response, jsonify
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
        cat = request.args.get('cat', '')
        
        # Handle empty searches based on category
        if not query_param or query_param.strip() == '':
            if cat == '2000':  # Movie category
                query_param = 'Akira'  # Default to a popular anime movie
                logger.info("Empty movie category search, defaulting to 'Akira'")
            else:  # TV or general
                query_param = 'given'  # Default to a popular TV anime
                logger.info("Empty search query, defaulting to 'given'")
        
        processed_query = query_processor.process_search_query(query_param)
        logger.info(f"Processed search query: '{processed_query}' (original: '{query_param}', cat: {cat})")
        
        # Perform search with enhanced movie support
        # Use search_type based on category if specified
        search_type = "ANIME"
        if cat == '2000':
            # Hint that we're looking for movies
            search_type = "ANIME"  # Still use ANIME but the category will influence results
        
        result = search_service.perform_search(processed_query, search_type=search_type)
        
        # Handle the 5-tuple return value
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
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
            # Determine if we should force anime category based on the category filter
            force_anime = False
            if cat == '5000':  # TV category requested
                force_anime = True
            elif cat == '2000':  # Movie category requested
                force_anime = False
            else:
                # No specific category, use format to decide
                force_anime = anime_format != 'MOVIE'
            
            xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents, 
                                                anime_format=anime_format, year=year,
                                                force_anime_category=force_anime)
            return Response(xml, mimetype='application/xml')

    elif t == 'tvsearch':
        query_param = request.args.get('q', '')
        season = request.args.get('season')
        episode = request.args.get('ep')
        
        # Handle empty searches with a default popular anime
        if not query_param or query_param.strip() == '':
            query_param = 'given'  # Default to a popular TV anime
            logger.info("Empty TV search query, defaulting to 'given'")
        
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
        
        result = search_service.perform_search(processed_query, season, episode)
        
        # Handle the 5-tuple return value
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
        if not anilist_id or not processed_torrents:
            # Return empty but valid RSS instead of error for Prowlarr compatibility
            return Response(xml_service.build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        # Force anime category (5000) for Sonarr compatibility
        xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents, 
                                            season, episode, anime_format, year, 
                                            force_anime_category=True)
        return Response(xml, mimetype='application/xml')

    elif t == 'movie':
        query_param = request.args.get('q', '')
        
        # Handle empty searches with a default popular movie
        if not query_param or query_param.strip() == '':
            query_param = 'Spirited Away'  # Default to a popular anime movie
            logger.info("Empty movie search query, defaulting to 'Spirited Away'")
        
        processed_query = query_processor.process_search_query(query_param)
        logger.info(f"Movie search for: '{processed_query}'")
        
        result = search_service.perform_search(processed_query, search_type="ANIME")
        
        # Handle the 5-tuple return value
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
        if not anilist_id or not processed_torrents:
            return Response(xml_service.build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        # Use movie category (2000) for Radarr compatibility
        xml = xml_service.build_rss_enhanced(anilist_id, anime_name, processed_torrents, 
                                            anime_format=anime_format, year=year, 
                                            force_anime_category=False)
        return Response(xml, mimetype='application/xml')

    else:
        logger.error(f"Invalid request type: {t}")
        return Response("Invalid request", status=400)

@app.route('/mapping/update', methods=['POST'])
def force_mapping_update():
    """Force an immediate update of the mapping file from remote"""
    try:
        success = search_service.mapping_service.force_update()
        if success:
            stats = search_service.mapping_service.get_stats()
            return jsonify({
                'success': True,
                'message': 'Mapping file updated successfully',
                'stats': stats
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update mapping file from remote'
            }), 500
    except Exception as e:
        logger.error(f"Error forcing mapping update: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/mapping/stats')
def mapping_stats():
    """Get statistics about the current mapping configuration"""
    try:
        stats = search_service.mapping_service.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting mapping stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/mapping/reload', methods=['POST'])
def reload_mapping():
    """Reload mapping from local file (useful for testing local changes)"""
    try:
        search_service.mapping_service.reload_mappings()
        stats = search_service.mapping_service.get_stats()
        return jsonify({
            'success': True,
            'message': 'Local mapping file reloaded',
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error reloading mapping: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

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
    result = search_service.perform_search(processed_query, season, episode)
    
    # Handle the 5-tuple return value
    if len(result) == 5:
        anilist_id, anime_name, processed_torrents, anime_format, year = result
    else:
        anilist_id, anime_name, processed_torrents = result
        anime_format = None
        year = None
    
    if not anilist_id:
        return f"Could not find AniList ID for: {q}"
    
    # Get mapping stats
    mapping_stats = search_service.mapping_service.get_stats()
    
    result_text = f"<h3>Mapping Stats:</h3>"
    result_text += f"Total mappings: {mapping_stats['total_mappings']}<br>"
    result_text += f"Last update: {mapping_stats['last_update']}<br>"
    result_text += f"Remote URL: {mapping_stats['remote_url']}<br><br>"
    
    result_text += f"<h3>Search Results:</h3>"
    result_text += f"Found {len(processed_torrents)} torrents for {anime_name} ({anime_format}) (ID: {anilist_id}, Year: {year})<br>"
    result_text += f"Processed query: {processed_query}<br><br>"
    
    for i, torrent in enumerate(processed_torrents):
        result_text += f"Torrent {i+1}:<br>"
        if torrent.get('custom_name'):
            result_text += f"  - <b>Custom Name: {torrent['custom_name']}</b><br>"
        result_text += f"  - Movie: {torrent.get('is_movie', False)}<br>"
        result_text += f"  - Season Pack: {torrent['is_season_pack']}<br>"
        result_text += f"  - Seasons: {torrent['seasons']}<br>"
        result_text += f"  - Episodes: {torrent['episode_numbers']}<br>"
        result_text += f"  - Release Group: {torrent['release_group']}<br>"
        result_text += f"  - Size: {torrent['total_size'] / (1024**3):.2f} GB<br>"
        result_text += f"  - Files: {torrent['episode_count']}<br>"
        result_text += f"  - Is Custom: {torrent.get('is_custom_mapping', False)}<br><br>"
    
    return result_text

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=18621, debug=True)
