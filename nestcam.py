
"""Nest Cam Library"""

import json
import os
import requests
import sys
import urllib
import urllib2


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


class NestAccount(object):
    """Encapsulation of access to Nest API Server for a given Nest account."""
    @staticmethod
    def _err(msg, fatal=False):
        sys.stderr.write("Error: %s\n", msg)
        if fatal:
            sys.exit(1)

    def _updateCameras(self, validate=True):
        # query the API server
        #### FIXME handle 307 REDIRECT returns
        req = urllib2.Request(NEST_API_URL, None, self.headers)
        #### FIXME handle the 429 ERROR (Too Many Requests) here
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
            ####response = requests.get(AUTH_URL)
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
          JSON object with info for all of the cameras
        """
        self._updateCameras()
        return self.cams

    def cameraIds(self):
        """ Return the IDs of all Nest cameras for the logged-in account.

        Args:
          None

        Returns:
          List of IDs for all of the cameras
        """
        self._updateCameras()
        return self.cams.keys()

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

    def cameraNameLookup(self, camId):
        """ Get the name for the camera with the given ID.

        Args:
          camId: ID of the camera of interest

        Returns:
          (Long) name of the given camera
        """
        self._updateCameras()
        return self.getInfo(camId)['name_long']

    def cameraIdLookup(self, namePrefix):
        """ Get the ID(s) for the camera(s) who's name starts with a given string.

        Args:
          namePrefix: prefix for the name of the camera(s) of interest

        Returns:
          List of IDs for camera(s) with given name
        """
        self._updateCameras()
        return [v['device_id'] for k, v in self.cams.iteritems() if v['name'].lower().startswith(namePrefix.lower())]

    def snapshotUrlLookup(self, camId):
        """ Get the Snapshot URL for a given camera.

        Args:
          camId: ID of the camera of interest

        Returns:
          Snapshot URL for the camera with the given ID
        """
        info = self.getInfo(camId)
        return info['snapshot_url']

    def cameraInfo(self, camId):
        """ Return info for the given camera.

        Args:
          camId: ID of the camera of interest

        Returns:
          JSON object containing information about the given camera
        """
        self._updateCameras()
        if camId not in self.cams:
            raise APIError("Camera with ID {0} not found".format(camId))
        info = self.cams[camId]
        return info

    def getSnapshot(self, camId):
        """ Capture an image from the given camera.

        Args:
          camId: ID of the camera of interest

        Returns:
          JPEG image
        """
        url = self.snapshotUrlLookup(camId)
        r = requests.get(url)
        r.raise_for_status()

        if r.headers['content-length'] == 0:
            # got empty image with success code, so throw an exception
            raise requests.ConnectionError("Unable to get image from camera")
        if r.headers['Content-Type'] != 'image/jpeg':
            raise ValueError("Did not return a JPEG Image")
        image = r.content
        return image


#
# TEST CODE
#

if __name__ == '__main__':
    from test_config import PRODUCT_ID, PRODUCT_SECRET, CA_FILE, CAM_NAMES_MAP, IMG_DIR
    #### from test_config import AUTH_URL

    nums = []
    nest = NestAccount(PRODUCT_ID, PRODUCT_SECRET, CA_FILE)

    cams = nest.cameras()
    num = len(cams)
    nums.append(num)
    print("Cameras: {0}".format(num))
    for camId, camInfo in cams.iteritems():
        print("    Camera: {0}".format(camInfo['name_long']))
        json.dump(camInfo, sys.stdout, indent=4, sort_keys=True)
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

    print("Snapshot URL:")
    for camId, camName in camsNameMap.iteritems():
        url = nest.snapshotUrlLookup(camId)
        print("    {0}: {1}".format(camName, url))

    print("CameraIdsLookup:")
    for name, numIds in CAM_NAMES_MAP.iteritems():
        ids = nest.cameraIdLookup(name)
        print("    {0}: {1}".format(name, ids))
        if len(ids) != numIds:
            print("ERROR: got {0} IDs, wanted {1}".format(len(ids), numIds))
            sys.exit(1)

    print("Camera Info:")
    for camId, camName in camsNameMap.iteritems():
        info = nest.cameraInfo(camId)
        print("    {0}:".format(camName))
        json.dump(info, sys.stdout, indent=4, sort_keys=True)
        print("")
        break

    print("Snapshot:")
    for camId, camName in camsNameMap.iteritems():
        path = os.path.join(IMG_DIR, camName + camId)
        img = nest.getSnapshot(camId)
        with open(path, "w") as outFile:
            outFile.write(img)
            print("    {0}".format(path))

    print("SUCCESS")
