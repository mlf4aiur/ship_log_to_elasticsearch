#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
abspath = os.path.abspath(os.path.dirname(__file__))
os.chdir(abspath)
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import pyes
import ConfigParser
import time
import datetime
import re
import inspect
import logging
import logging.config
import traceback


# init logging facility
logconf = "conf/logging.cfg"
logging.config.fileConfig(logconf)


HEADERS = ("host",
           "timestamp",
           "method",
           "uri",
           "protocol",
           "status",
           "bytes",
           "referer",
           "user_agent")


# 66.249.73.69 - - [08/Aug/2012:12:10:10 +0400] "GET / HTTP/1.1" 200 23920 "-" "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
access_log_pattern = re.compile(
    r"(?P<host>[\d\.]+)\s"
    r"(?P<identity>\S*)\s"
    r"(?P<user>\S*)\s"
    r"(?P<time>\[.*?\])\s"
    r'"(?P<request>.*?)"\s'
    r"(?P<status>\d+)\s"
    r"(?P<bytes>\S*)\s"
    r'"(?P<referer>.*?)"\s'
    r'"(?P<user_agent>.*?)"\s*'
)


class HTTPDateTime(object):
    def __init__(self, time_string):
        """
        HTTP date time object
        @input time_string: [08/Aug/2012:12:10:10 +0400]
        """
        self.time_string = time_string
        self.altzone = time.altzone
        self.isodate = "%Y-%m-%dT%H:%M:%SZ"
        self.fmt = "[%d/%b/%Y:%H:%M:%S"
        return

    def to_unixtimestamp(self):
        (date_time, timezone) = self.time_string.split()
        offset = int(timezone[:-1]) / 100 * 60 * 60
        unixtimestamp = int(time.mktime(time.strptime(date_time, self.fmt)))
        unixtimestamp = unixtimestamp - self.altzone - offset
        return unixtimestamp

    def to_isodate(self):
        return time.strftime(self.isodate, time.gmtime(self.to_unixtimestamp()))


def log_entry_getter():
    for line in sys.stdin:
        match= access_log_pattern.match(line)
        if match:
            yield match.groupdict()


def log_doc_getter():
    logger = logging.getLogger(inspect.stack()[0][3])
    for fields in log_entry_getter():
        time = fields.get("time", "[01/Jan/1970:10:10:10 +0000]")
        http_datetime = HTTPDateTime(time)

        try:
            timestamp = http_datetime.to_isodate()
        except Exception:
            timestamp = "1970-01-01T10:10:10Z"

        try:
            request = fields.get("request")
            (method, uri, protocol) = request.split()
        except Exception:
            exstr = traceback.format_exc()
            logger.debug(request)
            logger.debug(exstr)

        doc = dict(host=fields.get("host", "1.1.1.1"),
                   timestamp=timestamp,
                   method=method,
                   uri=uri,
                   protocol=protocol,
                   status=fields.get("status", 000),
                   bytes=fields.get("bytes", 0),
                   referer=fields.get("referer", "-"),
                   user_agent=fields.get("user_agent", "-"))
        yield doc

def get_index_name():
    return datetime.datetime.now().strftime("access-%Y%m")


def create_index(conn, index_name):
    """
    Create an index
    dependent template:
    curl -XPUT http://localhost:9200/_template/template_access/ -d @conf/elasticsearch_template.json
    curl -XGET http://localhost:9200/_template/template_access/
    curl -XDELETE http://localhost:9200/_template/template_access/
    """
    try:
        conn.create_index(index_name)
    except pyes.exceptions.IndexAlreadyExistsException:
        pass


def put_index(conn, doc_type, mapping, index_name):
    conn.put_mapping(doc_type=doc_type,
                     mapping=mapping,
                     indices=[index_name])



def index_log(conn, index_name, doc_type):
    logger = logging.getLogger(inspect.stack()[0][3])
    for doc in log_doc_getter():
        try:
            conn.index(doc=doc, index=index_name, doc_type=doc_type, bulk=True)
        except Exception:
            exstr = traceback.format_exc()
            logger.warn(exstr)
            logger.warn("can not index: %s" % (str(doc)))
    return


def main():
    logger = logging.getLogger(inspect.stack()[0][3])
    logger.info("start")
    config = ConfigParser.RawConfigParser()
    config.read("conf/main.cfg")
    es_host = config.get("elasticsearch", "host").split(",")
    bulk_size = config.getint("elasticsearch", "bulk_size")
    doc_type = config.get("elasticsearch", "doc_type")

    # Creating a connection
    conn = pyes.ES(es_host, timeout=30.0, bulk_size=bulk_size)
    index_name = get_index_name()
    create_index(conn, index_name)
    put_index(conn, doc_type, None, index_name)
    index_log(conn, index_name, doc_type)
    conn.refresh([index_name])
    logger.info("done")
    return


if __name__ == "__main__":
    main()
