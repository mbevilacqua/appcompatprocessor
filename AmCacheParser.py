#!/usr/bin/python
# Ripped by Matias Bevilacqua from Will Ballenthin's python-registry amcache sample
# Refactored to work with libregf python bindings for speed purposes, added support for Windows 10

#    The origianl code was part of the python-registry module.
#
#   Copyright 2015 Will Ballenthin <william.ballenthin@mandiant.com>
#                    while at Mandiant <http://www.mandiant.com>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import settings
import logging
from datetime import datetime
from collections import namedtuple
import os
import sys
try:
    import pyregf
except ImportError:
    if settings.__PYREGF__:
        settings.__PYREGF__ = False
        print "Ooops seems you don't have pyregf!"
        print "AmCache loading support will be disabled"
else: settings.__PYREGF__ = True

try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

from appAux import update_progress, chunks, loadFile, checkLock
# minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
logger = logging.getLogger(__name__)

Field = namedtuple("Field", ["name", "getter"])


def make_value_getter(value_name):
    """ return a function that fetches the value from the registry key """
    def _value_getter(key):
        try:
            return key.get_value_by_name(value_name).get_data_as_string()
        except:
            return None
    return _value_getter

def make_integer_value_getter(value_name):
    """ return a function that fetches the value from the registry key """
    def _value_getter(key):
        try:
            return key.get_value_by_name(value_name).get_data_as_integer()
        except:
            return None
    return _value_getter

def make_windows_timestamp_value_getter(value_name):
    """
    return a function that fetches the value from the registry key
      as a Windows timestamp.
    """
    f = make_value_getter(value_name)
    def _value_getter(key):
        try:
            if key.get_value_by_name(value_name) != None:
                return parse_windows_timestamp(key.get_value_by_name(value_name).get_data_as_integer() or 0)
            else: return datetime.min
        except ValueError:
            return datetime.min
    return _value_getter


def parse_unix_timestamp(qword):
    return datetime.fromtimestamp(qword)


def parse_windows_timestamp(qword):
    try:
        return datetime.utcfromtimestamp(float(qword) * 1e-7 - 11644473600 )
    except ValueError:
        return datetime.min


def make_unix_timestamp_value_getter(value_name):
    """
    return a function that fetches the value from the registry key
      as a UNIX timestamp.
    """
    f = make_value_getter(value_name)
    def _value_getter(key):

        try:
            if key.get_value_by_name(value_name) != None:
                return parse_unix_timestamp(key.get_value_by_name(value_name).get_data_as_integer() or 0)
            else: return datetime.min
        except ValueError:
            return datetime.min
    return _value_getter


UNIX_TIMESTAMP_ZERO = parse_unix_timestamp(0)
WINDOWS_TIMESTAMP_ZERO = parse_windows_timestamp(0)


# via: http://www.swiftforensics.com/2013/12/amcachehve-in-windows-8-goldmine-for.html
#Product Name    UNICODE string
#==============================================================================
#0   Product Name    UNICODE string
#1   Company Name    UNICODE string
#2   File version number only    UNICODE string
#3   Language code (1033 for en-US)  DWORD
#4   SwitchBackContext   QWORD
#5   File Version    UNICODE string
#6   File Size (in bytes)    DWORD
#7   PE Header field - SizeOfImage   DWORD
#8   Hash of PE Header (unknown algorithm)   UNICODE string
#9   PE Header field - Checksum  DWORD
#a   Unknown QWORD
#b   Unknown QWORD
#c   File Description    UNICODE string
#d   Unknown, maybe Major & Minor OS version DWORD
#f   Linker (Compile time) Timestamp DWORD - Unix time
#10  Unknown DWORD
#11  Last Modified Timestamp FILETIME
#12  Created Timestamp   FILETIME
#15  Full path to file   UNICODE string
#16  Unknown DWORD
#17  Last Modified Timestamp 2   FILETIME
#100 Program ID  UNICODE string
#101 SHA1 hash of file


# note: order here implicitly orders CSV column ordering cause I'm lazy
FIELDS = [
    Field("path", make_value_getter("15")),
    Field("sha1", make_value_getter("101")),
    Field("size", make_integer_value_getter("6")),
    Field("file_description", make_value_getter("c")),
    Field("first_run", lambda key: key.get_last_written_time()),
    Field("created_timestamp", make_windows_timestamp_value_getter("12")),
    Field("modified_timestamp", make_windows_timestamp_value_getter("11")),
    Field("modified_timestamp2", make_windows_timestamp_value_getter("17")),
    Field("linker_timestamp", make_unix_timestamp_value_getter("f")),
    Field("product", make_value_getter("0")),
    Field("company", make_value_getter("1")),
    Field("pe_sizeofimage", make_integer_value_getter("7")),
    Field("version_number", make_value_getter("2")),
    Field("version", make_value_getter("5")),
    Field("language", make_integer_value_getter("3")),
    Field("header_hash", make_value_getter("8")),
    Field("pe_checksum", make_integer_value_getter("9")),
    Field("id", make_integer_value_getter("100")),
    Field("switchbackcontext", make_integer_value_getter("4")),
]

# note: order here implicitly orders CSV column ordering cause I'm lazy
FIELDS_win10 = [
    Field("path", make_value_getter("LowerCaseLongPath")),
    Field("sha1", make_value_getter("FileId")),
    Field("size", make_integer_value_getter("Size")),
    Field("file_description", lambda key: None),
    Field("first_run", lambda key: key.get_last_written_time()),
    Field("created_timestamp", lambda key: datetime.min),
    Field("modified_timestamp", lambda key: datetime.min),
    Field("modified_timestamp2", lambda key: datetime.min),
    Field("linker_timestamp", lambda key: datetime.min),
    Field("product", lambda key: None),
    Field("company", lambda key: None),
    Field("pe_sizeofimage", lambda key: None),
    Field("version_number", lambda key: None),
    Field("version", lambda key: None),
    Field("language", lambda key: None),
    Field("header_hash", lambda key: None),
    Field("pe_checksum", lambda key: None),
    Field("id", lambda key: None),
    Field("switchbackcontext", lambda key: None),


]

ExecutionEntry = namedtuple("ExecutionEntry", map(lambda e: e.name, FIELDS))
ExecutionEntry_win10 = namedtuple("ExecutionEntry_win10", map(lambda e: e.name, FIELDS_win10))


def parse_execution_entry(key):
    # Note: Change required to make it work on python 2.6.6:
    # return(ExecutionEntry(**{e.name:e.getter(key) for e in FIELDS}))
    ret = {}
    for e in FIELDS:
        ret[e.name] = e.getter(key)

    return ExecutionEntry(**(ret))

def parse_execution_entry_win10(key):
    # Note: Change required to make it work on python 2.6.6:
    # return(ExecutionEntry(**{e.name:e.getter(key) for e in FIELDS}))
    ret = {}
    for e in FIELDS_win10:
        ret[e.name] = e.getter(key)

    return ExecutionEntry_win10(**(ret))

class NotAnAmcacheHive(Exception):
    pass

def get_sub_keys(key, path=''):
    # iterate all sub-keys of key returning (key,path)
    num_keys = key.get_number_of_sub_keys()

    for i in xrange(num_keys):
        cur_key = key.get_sub_key(i)
        new_path = os.path.join(path, cur_key.get_name())
        yield (cur_key, new_path)

        for result in get_sub_keys(cur_key, new_path):
            yield result

def parse_execution_entries(regf):
    format_win10_hive = False
    if regf.get_key_by_path(r'Root\InventoryApplicationFile') is not None:
        format_win10_hive = True
    else:
        if regf.get_key_by_path(r'Root\File') is None:
            raise NotAnAmcacheHive()

    ret = []

    if format_win10_hive:
        sub_keys = get_sub_keys(regf.get_key_by_path(r'Root\InventoryApplicationFile'))
        for filekey, volumePath in sub_keys:
            ret.append(parse_execution_entry_win10(filekey))
    else:
        sub_keys = get_sub_keys(regf.get_key_by_path(r'Root\File'))
        for volumekey, volumePath in sub_keys:
            for filekey in get_sub_keys(volumekey):
                ret.append(parse_execution_entry(filekey[0]))

    return ret


TimelineEntry = namedtuple("TimelineEntry", ["timestamp", "type", "entry"])

def _processAmCacheFile(fileFullPath):
    file_object = open(fileFullPath, "rb")
    regf_file = pyregf.file()
    regf_file.open_file_object(file_object, "r")

    try:
        ee = parse_execution_entries(regf_file)
    except NotAnAmcacheHive:
        logger.error("doesn't appear to be an Amcache.hve hive")
        return
    finally:
        regf_file.close()
        file_object.close()

    return ee


def _processAmCacheFile_StringIO(data):
    regf_file = pyregf.file()
    regf_file.open_file_object(data, "r")

    try:
        ee = parse_execution_entries(regf_file)
    except NotAnAmcacheHive:
        logger.error("doesn't appear to be an Amcache.hve hive")
        return
    finally:
        regf_file.close()

    return ee

if __name__ == "__main__":
    fileFullPath = str(sys.argv[1])
    file_object = loadFile(fileFullPath)
    regf_file = pyregf.file()
    regf_file.open_file_object(file_object, "r")

    try:
        ee = parse_execution_entries(regf_file)
    except NotAnAmcacheHive:
        print("doesn't appear to be an Amcache.hve hive")
    finally:
        regf_file.close()
        file_object.close()
