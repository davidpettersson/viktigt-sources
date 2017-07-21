#!/usr/bin/python3.4
import requests
import xml.etree.ElementTree as ET
import warnings
import io
import sys
from subprocess import Popen, PIPE, DEVNULL

import cap_api

POST_URL='http://viktigt.vdrift.se/vicky/alerts'

ns = {
    'ns0': 'http://www.w3.org/2005/Atom',
    'cap': 'urn:oasis:names:tc:emergency:cap:1.2'
}

ET.register_namespace('cap', 'urn:oasis:names:tc:emergency:cap:1.2')

r = requests.get('http://api.krisinformation.se/v1/feed?format=xml')
if r.status_code == 200:
    feed = ET.fromstring(r.text)

if feed:
    # Create the ATOM feed root element and set it up
    for entry in feed.iterfind('ns0:entry', ns):
        for entry_id in entry.findall('ns0:id', ns):
            url = entry_id.text
            r = requests.get(url)
            if r.status_code != 200:
                print("Unable to fetch " + url + " - status " + str(r.status_code))
                continue
            alert = ET.fromstring(r.text)

            alert = ET.fromstring(r.text)
            sender = alert.find('cap:sender', ns)
            for info in alert.findall('cap:info', ns):
                # senderName must be before headline!
                headline = info.find('cap:headline', ns)
                sender_name = info.find('cap:senderName', ns)
                info.remove(sender_name)
                info.insert(list(info).index(headline), sender_name)

                # area has no child named Type
                area_list = info.findall('cap:area', ns)
                for area in area_list:
                    area_type = area.find('cap:Type', ns)
                    # Stating things like area 'Sweden' and then a county is not... 
                    # really helpful.... Try to avoid plotting those.
                    if area_type.text is 'Sovereign country' and len(area_list) > 1:
                        info.remove(area)
                        continue
                    else:
                        area.remove(area_type)

                    # Order matters! Area is last!
                    info.remove(area)
                    info.append(area)

                    # Polygon lists polygons directly, Polygons doesn't exist
                    polygon = area.find('cap:Polygon', ns)
                    if polygon:
                        to_remove = polygon.find('cap:Polygon', ns)
                        data = to_remove.find('cap:Polygons', ns)
                        polygon.text = data.text
                        polygon.remove(to_remove)
                        polygon.tag = 'cap:polygon'

            # add data to array
            data = ET.tostring(alert, encoding='utf-8', method='xml').decode('utf-8')

            process = Popen(['xmllint', '--schema', 'schemas/CAP-v1.2.xsd', '--noout', '-'], 
                    stdin=PIPE, stderr=PIPE, stdout=DEVNULL)
            process.stdin.write(data.encode('utf-8') + b'\n')
            process.stdin.close()
            process.wait()
            if process.returncode != 0:
                error_msg = process.stderr.read()
                print('Error, ' + url + ' did not validate!')
                print('---\n' + data + '\n---\n' + error_msg.decode('utf-8'))
                continue

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always')
                new_alert = cap_api.parse(io.StringIO(data), silence=True)
                for v in w:
                    print (str(v))
            output = io.StringIO()
            new_alert.export(output, 0)
            data_to_send = output.getvalue().encode('utf-8')
            r = requests.post(POST_URL, data=data_to_send)
            if r.status_code == 500:
                print('Internal server error, shutting down.')
                sys.exit(1)
            if r.status_code == 400:
                print("Failed to post " + str(r.status_code) + ": " + data_to_send.decode('utf-8') + " ----")

else:
    print('Failed to retrive all data!')
