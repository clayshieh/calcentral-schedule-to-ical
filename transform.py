from __future__ import print_function
from builtins import input

import json
from icalendar import Calendar, Event, vText
from icalendar.cal import Component
from dateutil import parser as du_parser
from dateutil.tz import tzlocal, tzutc
import pytz
import datetime
import getpass
import requests
import re
import sys

headers = {
    'Origin': 'https://auth.berkeley.edu',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.8,zh-CN;q=0.6,zh-TW;q=0.4',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Cache-Control': 'max-age=0',
    'Referer': 'https://auth.berkeley.edu/cas/login?service=https%3A%2F%2Fcalcentral.berkeley.edu%2Fauth%2Fcas%2Fcallback%3Furl%3Dhttps%253A%252F%252Fcalcentral.berkeley.edu%252F',
    'Connection': 'keep-alive',
}

def calnet_login(username, password):
    s = requests.Session()
    login_url = 'https://auth.berkeley.edu/cas/login?service=https%3A%2F%2Fcalcentral.berkeley.edu%2Fauth%2Fcas%2Fcallback%3Furl%3Dhttps%253A%252F%252Fcalcentral.berkeley.edu%252F'
    response = s.get(login_url)

    if response.status_code == 200:
        execution_re = r'<input type=\"hidden\" name=\"execution\" value=\"(.*?)\"/>'
        execution_val = re.search(execution_re, response.text)
        try:
            execution_val = execution_val.group(1)
        except IndexError:
            raise Exception("Execution value not found")

        data = "username={}&password={}&execution={}&_eventId=submit&geolocation=&submit=Sign+In".format(username, password, execution_val)
        login_response = s.post(login_url, headers=headers, data=data, cookies=response.cookies)
        if login_response.url == 'https://calcentral.berkeley.edu/':
            return s

    raise Exception('CalNet login failed')

def get_userdata(session):
    schedule_response = session.get('https://calcentral.berkeley.edu/college_scheduler/student/UGRD/2168')
    matches = re.findall('jsonData = (.*?);\s*Scheduler.initialize', schedule_response.text, re.DOTALL)
    return json.loads(matches[0])

vtimezone_str = \
"""BEGIN:VTIMEZONE
TZID:America/Los_Angeles
X-LIC-LOCATION:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
TZNAME:PDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
TZNAME:PST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

timezone = Component.from_ical(vtimezone_str)

weekday_abbrv_converter = {"U": "SU", "M": "MO", "T": "TU", "W": "WE", "R": "TH", "F": "FR", "S": "SA"}

def make_calender(userdata_json):
    cal = Calendar()
    cal.add_component(timezone)
    pacific_time = pytz.timezone('America/Los_Angeles') # Berkeley uses Pacific time
    for section in userdata_json['currentSectionData']:
        dept, course_number, section_number, ccn = section['subjectId'], section['course'], section['sectionNumber'], section['id']
        section_dept_and_number = "{} {}".format(dept, course_number)
        if len(section['meetings']) == 0:
            print("warning: Your {} has no meeting, ignored in calender".format(section_dept_and_number))
            continue
        meeting = section['meetings'][0]
        meeting_type = meeting['meetingType']
        start_date, end_date = du_parser.parse(meeting['startDate']), du_parser.parse(meeting['endDate'])
        start_time, end_time = datetime.datetime.strptime(str(meeting['startTime']), "%H%M"), datetime.datetime.strptime(str(meeting['endTime']), "%H%M")
        dtstart = pacific_time.localize(start_date.replace(hour=start_time.hour, minute=start_time.minute, tzinfo=None))
        dtend = pacific_time.localize(start_date.replace(hour=end_time.hour, minute=end_time.minute, tzinfo=None))
        byday = [weekday_abbrv_converter[x] for x in meeting['daysRaw']]
        location = meeting['location']
        event_name = "{} {} {}".format(section_dept_and_number, meeting_type, section_number)
        if len(byday) == 0:
            print("warning: Your {} has no appointed time, ignored in calender".format(event_name))
            continue
        event = Event()
        event.add('summary', event_name)
        event.add('dtstart', dtstart)
        event.add('dtend', dtend)
        event['location'] = vText(location)
        event.add('rrule', {'freq': 'weekly', 'until': end_date, 'byday': byday})
        cal.add_component(event)
    return cal

def main(filename):
    username = input('CalNet ID:')
    password = getpass.getpass()
    session = calnet_login(username, password)
    userdata_json = get_userdata(session)
    calender = make_calender(userdata_json)
    text = calender.to_ical()
    with open(filename, 'wb+') as f:
        f.write(text)
    print("Schedule saved to {}".format(filename))

import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate ical from calcentral scheduler planner')
    parser.add_argument('-o', '--outfile', type=str, dest="outfile",
                        default="schedule.ics",
                        help="ouput filename")
    options = parser.parse_args()
    main(options.outfile)
