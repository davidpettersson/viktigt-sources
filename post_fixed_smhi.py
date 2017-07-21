#!/usr/bin/python3.4
import requests
import xml.etree.ElementTree as ET
import copy
import io
import sys
from subprocess import Popen, PIPE, DEVNULL
import warnings

# generateDS generated cap grammar
import cap_api

POST_URL='http://viktigt.vdrift.se/vicky/alerts'

ns = {
    'smhi': 'urn:se:smhi:cap:metadata',
    'cap': 'urn:oasis:names:tc:emergency:cap:1.2'
}

def parse_pair(s):
    a, b = s.split(' ')
    return a, b

def parse_poly(poly_s):
    no_polygon = poly_s.strip()
    in_parts = no_polygon.split(',')
    poly = list(map(parse_pair, in_parts))
    return poly

def wash_stray_parenthesis(s):
    if s[0] == '(':
        s = s[1:]
    if s[-1] == ')':
        s = s[:-1]
    return s

def parse_polys(polys_s):
    # Remove POLYGON( <DATA> )
    no_polygon = polys_s.strip()[8:-1]
    parts = no_polygon.split('),(')
    parsed = map(parse_poly, map(wash_stray_parenthesis, parts))
    return list(parsed)

def handle_event_codes(old_info, new_info):
    new_event_codes = []
    old_event_codes = []

    for event_code in old_info.get_eventCode():
        # Nothing handles _sv-SE suffixes, lets remove them.
        if event_code.get_valueName()[-6:] == '_sv-SE':
            event_code.set_valueName(event_code.get_valueName()[:-6])
            old_event_codes.append(event_code)
        else:
            new_event_codes.append(event_code)

    old_info.set_eventCode(old_event_codes)
    new_info.set_eventCode(new_event_codes)

def handle_parameters(old_info, new_info):
    old_parameters = []
    new_parameters = []

    for parameter in old_info.get_parameter():
        # Stating english in them, is not standard.
        if parameter.get_valueName()[:11] == 'system_eng_':
            val = parameter.get_value()
            # Parameters are optional, no such entry == no such data.
            if not (val[:11] == 'No English ' and val[-10:] == ' available'):
                parameter.set_valueName('system_' + parameter.get_valueName()[11:])
                new_parameters.append(parameter)
        else:
            old_parameters.append(parameter)

    old_info.set_parameter(old_parameters)
    new_info.set_parameter(new_parameters)

ET.register_namespace('cap', 'urn:oasis:names:tc:emergency:cap:1.2')

r = requests.get('https://opendata-download-warnings.smhi.se/api/version/2/districtviews/land.xml')
if r.status_code == 200:
    land = ET.fromstring(r.text)
    lookup = {entry.find('smhi:id', ns).text: 
        parse_polys(entry.find('smhi:geometry/smhi:polygon', ns).text)
            for entry in land.iterfind('smhi:district_view', ns)}

r = requests.get('https://opendata-download-warnings.smhi.se/api/version/2/districtviews/sea.xml')
if r.status_code == 200:
    sea = ET.fromstring(r.text)
    lookup.update({entry.find('smhi:id', ns).text: 
        parse_polys(entry.find('smhi:geometry/smhi:polygon', ns).text)
            for entry in sea.iterfind('smhi:district_view', ns)})

r = requests.get('https://opendata-download-warnings.smhi.se/api/version/2/alerts.xml')
if r.status_code == 200:
    alerts = ET.fromstring(r.text)

if land and sea and alerts:
    for entry in alerts.iterfind('cap:alert', ns):
        data = ET.tostring(entry, encoding='utf-8', method='xml').decode('utf-8')
        process = Popen(['xmllint', '--schema', 'schemas/CAP-v1.2.xsd', '--noout', '-'],
                stdin=PIPE, stderr=PIPE, stdout=DEVNULL)
        process.stdin.write(data.encode('utf-8') + b'\n')
        process.stdin.close()
        process.wait()
        if process.returncode != 0:
            error_msg = process.stderr.read()
            print('Error, did not validate!')
            print('---\n' + data + '\n---\n' + error_msg.decode('utf-8'))
            continue

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            alert = cap_api.parse(io.StringIO(data), silence=True)
            for v in w:
                print(str(v))

        # Avoid problems with weak references
        infos = list(alert.get_info())
        for info in infos:
            for area in info.get_area():
                polygon = area.get_polygon()
                if not polygon:
                    # If no polygon is defined, try to locate it from the land
                    # and sea data.
                    areaDesc = area.get_areaDesc()
                    # areaDesc can be two ids, comma separated
                    area_ids = areaDesc.split(',')
                    if not area_ids:
                        area_ids = [areaDesc]
                    for area_id in area_ids:
                        for polys in lookup[area_id]:
                            formatted_text = ' '.join(map(lambda x: '%s,%s' % x, polys))
                            area.add_polygon(formatted_text)

            # here we copy and create a new info section for en-US (the default language)
            new_info = copy.copy(info) # deepcopy will not work for some reason...
            new_info.set_language('en-US')

            handle_event_codes(info, new_info)
            handle_parameters(info, new_info)
            # Add the new alert block
            alert.add_info(new_info)

        output = io.StringIO()
        alert.export(output, 0)
        data_to_send = output.getvalue().encode('utf-8')

        r = requests.post(POST_URL, data=data_to_send)
        if r.status_code == 500:
            print('Internal server error, shutting down.')
            sys.exit(1)
        if r.status_code == 400:
            print("Failed to post " + str(r.status_code) + ": " + data_to_send.decode('utf-8') + " ----")
else:
    print('Failed to retrive all data!')

  
