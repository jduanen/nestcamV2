
"""Nest Cam Library"""

import json
import requests
import sys
import urllib
import urllib2

from flask import request


NEST_AUTH_URL = "https://home.nest.com/login/oauth2"
NEST_ACCESS_TOKEN_URL = "https://api.home.nest.com/oauth2/access_token"
NEST_API_URL = "https://developer-api.nest.com"

#### TODO remove this when the using function is removed -- in the mean time, make it part of the config
TOKEN_FILE_PATH = "./token.txt"


class NestCamLibError(Exception):
    """Base class for exceptions in this module."""
    pass


class APIError(NestCamLibError):
    """Error class for exceptions in calling the Nest API Server."""
    def __init__(self, result):
        self.result = {"Error": result}


# Encapsulation of a Nest Camera
class NestCamera(object):
    def __init__(self, cookies, info):
        self.cookies = cookies
        self.info = info
        self.uuid = info['uuid']

    def name(self):
        return self.info['name']

    def id(self):
        return self.info['id']

    def capabilities(self):
        return self.info['capabilities']

    #### TODO add methods to get/set camera properties

    def dump(self):
        print("Camera: {0} - {1}".format(self.info['name'], self.info['uuid']))
        json.dump(self.info, sys.stdout, indent=4, sort_keys=True)
        print("\n")

    #### TODO method to grab a frame -- on event, periodically, log to file,...
    #### TODO figure out what to do with the seconds arg
    ####      (i.e.,: when to capture image in seconds from epoch)
    #### TODO figure out if we can specify image height too/instead of width?
    def grabFrame(self, width=720):
        path = "https://nexusapi.camera.home.nest.com/get_image"
        params = "uuid={0}&width={1}".format(self.uuid, width)
        r = requests.get(path, params=params, cookies=self.cookies)
        r.raise_for_status()

        if config['testing']:
            print("Headers: {0}".format(r.headers))
        if r.headers['content-length'] == 0:
            # got empty image with success code, so throw an exception
            raise ConnectionError('Unable to get image from camera')
        image = r.content
        return image

    #### TODO methods for events -- get last, wait for, log, etc.
    def getEvents(self, startTime, endTime=None):
        if not endTime:
            endTime = int(time.time())
        path = "https://nexusapi.camera.home.nest.com/get_cuepoint"
        params = "uuid={0}&start_time={1}&end_time={2}".format(self.uuid,
                                                               startTime,
                                                               endTime)
        r = requests.get(path, params=params, cookies=self.cookies)
        r.raise_for_status()
        print("RESPONSE: {0}\n".format(r))
        return r.json()

    #### TODO methods for events -- get last, wait for, log, etc.


class NestAccount(object):
    """Encapsulation of access to Nest API Server for a given Nest account."""
    @staticmethod
    def _err(msg, fatal=False):
        sys.stderr.write("Error: %s\n", msg)
        if fatal:
            sys.exit(1)

    def _updateCameras(self, validate=True):
        # query the API server
        req = urllib2.Request(NEST_API_URL, None, self.headers)
        response = urllib2.urlopen(req, cafile=self.caFile)
        data = json.loads(response.read())

        if validate and 'devices' not in data:
            raise APIError("Nest account has no devices")
        devices = data["devices"]

        if validate and 'cameras' not in devices:
            raise APIError("Nest account has no cameras")
        self.cams = devices["cameras"]

        # verify the account has at least one Nest Camera
        if validate and len(self.cams.keys()) < 1:
            raise APIError("Nest account has no cameras")

    def __init__(self, productId, productSecret, caFile=None):
        """ Create connection to the NestCam API server.

        Args:
          productId: ID of Nest Developer product.
          productSecret: Secret for Nest Developer product.
          caFile: path to CA file (if None, look in default location).

        Returns:
          Newly created NestAccount object
        """
        self.caFile = caFile

        # Login to get the access token
        def _login():
            #### FIXME find a way to do the login automatically
            # login to the NestCam API server and get auth code
            queryStr = {
                'client_id': productId,
                'state':     'STATE'
            }
            response = requests.get(NEST_AUTH_URL, params=queryStr)
            print("{0}".format(response))
            print("C: {0}".format(response.content))
            ####authCode = request.args.get("code")
            authCode = None

            # get the access token
            data = urllib.urlencode({
                'client_id':     productId,
                'client_secret': productSecret,
                'code':          authCode,
                'grant_type':    'authorization_code'
            })
            req = urllib2.Request(NEST_ACCESS_TOKEN_URL, data)
            response = urllib2.urlopen(req, cafile=self.caFile)
            data = json.loads(response.read())
            token = data['access_token']
            return token

        # Read the access token from a file
        #### TODO this is a temp hack, remove it when I figure out how to login
        def _readTokenFile(filePath):
            token = None
            with open(filePath, "r") as tokenFile:
                token = tokenFile.readline().strip()
            return token

        if False:
            token = _login()
        else:
            token = _readTokenFile(TOKEN_FILE_PATH)

        self.headers = {
            'Authorization': "Bearer {0}".format(token)
        }
        self._updateCameras()

    def cameras(self):
        """ Return info on all Nest cameras for the logged-in account.

        Args:
          None

        Returns:
          List of JSON objects with info on each camera
        """
        self._updateCameras()
        return self.cams.values()

    def cameraNames(self):
        """ Return the (long) names of all Nest cameras for the logged-in account.
        N.B. There's no requirement that camera names be unique

        Args:
          None

        Returns:
          List of long names of cameras
        """
        self._updateCameras()
        return [self.cams[c]['name'] for c in self.cams]

    def camerasNameMap(self):
        """ Return a map of the (unique) IDs of all Nest cameras for the logged-in account to their (long) names.

        Args:
          None

        Returns:
          Dict mapping camera names to their IDs
        """
        self._updateCameras()
        return {k: self.cams[k]['name'] for k in self.cams.keys()}

    def cameraIdLookup(self, namePrefix):
        """ Get the ID(s) for the camera(s) who's name starts with a given string.

        Args:
          namePrefix: prefix for the name of the camera(s) of interest

        Returns:
          List of IDs for camera(s) with given name
        """
        self._updateCameras()
        return [v['device_id'] for k, v in self.cams.iteritems() if v['name'].lower().startswith(name.lower())]


#
# TEST CODE
#

if __name__ == '__main__':
    from test_config import PRODUCT_ID, PRODUCT_SECRET, CA_FILE, CAM_NAMES_MAP

    nums = []
    nest = NestAccount(PRODUCT_ID, PRODUCT_SECRET, CA_FILE)

    cs = nest.cameras()
    num = len(cs)
    nums.append(num)
    print("Cameras: {0}".format(num))
    for c in cs:
        print("    Camera: {0}".format(c['name']))
        json.dump(c, sys.stdout, indent=4, sort_keys=True)
        print("")

    camNames = nest.cameraNames()
    num = len(camNames)
    nums.append(num)
    print("CameraNames: {0}".format(num))
    json.dump(camNames, sys.stdout, indent=4, sort_keys=True)
    print("")

    camsNameMap = nest.camerasNameMap()
    num = len(camsNameMap)
    nums.append(num)
    print("CamerasNameMap: {0}".format(num))
    json.dump(camsNameMap, sys.stdout, indent=4, sort_keys=True)
    print("")

    if len(set(nums)) != 1:
        print("ERROR: mismatch in number of cameras found {0}".format(nums))
        sys.exit(1)

    print("CameraIdsLookup:")
    for name, numIds in CAM_NAMES_MAP.iteritems():
        ids = nest.cameraIdLookup(name)
        print("    {0}: {1}".format(name, ids))
        if len(ids) != numIds:
            print("ERROR: got {0} IDs, wanted {1}".format(len(ids), numIds))
            sys.exit(1)

    print("SUCCESS")
