import requests
import sys

OSM_NOMINATIM_URL = 'http://nominatim.openstreetmap.org/search'

def lookup_polygon(search_query):
    params = {
        'q': search_query,
        'format': 'json',
        'polygon': 1,
        'addressdetails': 0,
    }
    headers = {
        'Accept-Language': 'sv-SE',
    }
    rsp = requests.get(OSM_NOMINATIM_URL, params=params, headers=headers)
    j = rsp.json()

    if len(j) == 0:
        return None

    if not 'polygonpoints' in j[0]:
        return None

    if search_query in j[0]['display_name']:
        return j[0]['polygonpoints']
    else:
        return None

if __name__ == '__main__':
    if len(sys.argv) == 2:
        lookup_polygon(sys.argv[1])
    else:
        print('usage: %s SEARCH_QUERY' % sys.argv[0])
