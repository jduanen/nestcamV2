#!/usr/bin/env python

"""Nest Cam Capture Tool"""

#### TODO
#### * make all defaults be in the 'config' dict and get overwritten
####   by cmdline opts
#### * make all/many config values be setable via cmd line opts
#### * enable logging and put logs into the code (instead of prints)
#### * restrict testing mode and do all prints with logs
#### * default to all cameras and add white-/black-list names/ids to config -- all, only these, all except these


import argparse
import collections
from datetime import datetime
import glob
import json
import os
import sys
import time

import nestcam
import yaml


# N.B. Without a NestAware subscription, Google limits snapshots to 2 per minute (per-camera or per-site?)
GOOGLE_RATE_LIMIT = 30 * 1000   # 30 secs

# Initalize the default configuraton
config = {
    "testing": True,
    "cameraNames": [],    # use all cameras
    "delay": 10 * 60,     # 10 mins in between captures
    "maxFrames": 10,      # keep last 10 frames
    "numFrames": 0,	      # capture forever
    "outputPath": "/tmp/imgs/",  # save frames in /tmp/imgs/<camName>/<time>.jpg
    "productId": None,    # required
    "productSecret": None # required
}


# Merge a new dict into an old one, updating the old one (recursively).
def dictMerge(old, new):
    for k in new.keys():
        if (k in old and isinstance(old[k], dict) and
                isinstance(new[k], collections.Mapping)):
            dictMerge(old[k], new[k])
        else:
            old[k] = new[k]


#
# MAIN
#
def main():
    # Print error and exit
    def fatalError(msg):
        sys.stderr.write("Error: {0}\n".format(msg))
        sys.stderr.write("Usage: {0}\n".format(usage))
        sys.exit(1)

    usage = sys.argv[0] + "[-v] [-L] [-S [-Q <query>]] [-n <names>] " + \
        "[-c <confFile>] [-d <secs>] [-f <numFrames>] [-m <maxFrames>] " + \
        "[-o <outPath>] [-p <productId>] [-s <secret>]"
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '-L', '--list', action='store_true', default=False,
        help="list info on selected cameras (and return)")
    ap.add_argument(
        '-S', '--status', action='store_true', default=False,
        help="print info for the selected cameras (and don't capture images)")
    ap.add_argument(
        '-Q', '--query', action='store', type=str,
        help="jq-like query string to apply to Status output (defaults to '.' if not given")
    ap.add_argument(
        '-c', '--configFile', action='store',
        help="configuration input file path (defaults to './nestcam.conf'")
    ap.add_argument(
        '-d', '--delay', action='store', type=int,
        help="number of seconds to delay between sets of image grabs")
    ap.add_argument(
        '-f', '--numFrames', action='store', type=int,
        help="number of frames to capture (0=infinite)")
    ap.add_argument(
        '-m', '--maxFrames', action='store', type=int,
        help="maximum number of frames to save")
    ap.add_argument(
        '-n', '--names', action='store', type=str,
        help="comma-separated list of camera names")
    ap.add_argument(
        '-o', '--outputPath', action='store', type=str,
        help="base directory for output image files")
    ap.add_argument(
        '-p', '--productId', action='store', type=str,
        help="Nest Home product ID")
    ap.add_argument(
        '-s', '--secret', action='store', type=str,
        help="Nest Home product secret")
    ap.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="increase verbosity")
    options = ap.parse_args()

    # get the config file and merge with the defaults
    confFilePath = None
    if options.configFile:
        if not os.path.isfile(options.configFile):
            sys.stderr.write("Error: config file not found\n")
            sys.exit(1)
        confFilePath = options.configFile
    else:
        defaultPath = "./nestcam.conf"
        if os.path.isfile(defaultPath):
            confFilePath = defaultPath
        else:
            sys.stderr.write("Error: config file '%s' not found\n",
                             defaultPath)
            sys.exit(1)
    if confFilePath is not None:
        with open(confFilePath, 'r') as ymlFile:
            confFile = yaml.load(ymlFile)
        if confFile:
            dictMerge(config, confFile)

    # overwrite values from defaults and config file with cmd line options
    if options.names:
        config['cameraNames'] = options.names.strip().split(",")
    if options.delay:
        config['delay'] = options.delay
    if options.numFrames:
        config['numFrames'] = options.numFrames
    if options.maxFrames:
        config['maxFrames'] = options.maxFrames
    if options.outputPath:
        config['outputPath'] = options.outputPath
    if options.productId:
        config['productId'] = options.productId
    if options.secret:
        config['productSecret'] = options.secret

    # validate config values
    if config['numFrames'] < 0:
        fatalError("Number of frames to capture must be non-negative")
    if config['maxFrames'] < 0:
        fatalError("Number of frames to retain must be non-negative")
    if config['delay'] < 0:
        fatalError("Inter-frame delay must be non-negative")
    if not config['outputPath']:
        fatalError("Must provide output path")
    if not config['productId'] or not config['productSecret']:
        fatalError("Must provide Nest Home product ID and Secret")

    # instantiate the NestCam interface object
    tries = 3
    while tries > 0:
        try:
            nest = nestcam.NestAccount(config['productId'], config['productSecret'])
            break
        except Exception as e:
            if options.verbose > 0:
                sys.stderr.write("Warning: Failed to attach to NestCam server: {0}".
                                 format(e))
        tries -= 1
    if tries <= 0:
        fatalError("Unable to attach to NestCam server")

    # get ids for all of the selected cameras
    if not config['cameraNames']:
        config['cameraNames'] = nest.cameraNames()
        config['cameraIds'] = nest.cameraIds()
    else:
        config['cameraIds'] = []
        for camName in config['cameraNames']:
            camIds = nest.cameraIdLookup(camName)
            if camIds is None:
                fatalError("Non-existant camera '{0}'".format(camName))
            if len(camIds) != 1:
                fatalError("Ambiguous camera name '{0}': {1}".format(camName, camIds))
            config['cameraIds'].append(camIds[0])

    # validate and init the directories for all of the cameras' images
    if not os.path.exists(config['outputPath']):
        os.makedirs(config['outputPath'])
    for camId, camName in nest.camerasNameMap().iteritems():
        path = os.path.join(config['outputPath'], camName + camId)
        if not os.path.exists(path):
            os.makedirs(path)

    if options.verbose > 1:
        print("Configuration:")
        json.dump(config, sys.stdout, indent=4, sort_keys=True)
        print("")

    # get the current state of all the cameras associated with this account
    if options.verbose > 2:
        allCamIds = nest.cameraIds()
        print("All Camera Ids: {0}".format(allCamIds))

        allCamNames = nest.cameraNames()
        print("All Camera Names: {0}".format(allCamNames))

        allCamsMap = nest.camerasNameMap()
        print("Map of all Camera IDs to Names:")
        json.dump(allCamsMap, sys.stdout, indent=4, sort_keys=True)
        print("")

    camerasInfo = {k: v for k, v in nest.cameras().iteritems() if k in config['cameraIds']}
    if options.list:
        print("Cameras Info:")
        json.dump(camerasInfo, sys.stdout, indent=4, sort_keys=True)
        print("")
        sys.exit(0)

    # capture a frame from each camera in the list, writing the images to
    #  files in the given directory, wait the given amount of time, and repeat
    count = 0
    while True:
        for camId in config['cameraIds']:
            info = nest.cameraInfo(camId)
            name = info['name_long']
            ts = datetime.utcnow().isoformat()
            if options.verbose > 2:
                print("Timestamp: {0}".format(ts))
            if options.status:
                # get the status and don't capture an image
                if options.verbose:
                    print("Camera {0} Status:".format(name))
                #### TODO if there's a query filter, apply it (else emit the whole thing)
                json.dump(info, sys.stdout, indent=4, sort_keys=True)
                continue

            # capture an image
            if options.verbose:
                print("Capture image from camera {0}".format(name))
            try:
                img = nest.getSnapshot(camId)
            except Exception:
                continue
            if not img:
                continue

            # delete oldest frame if there are more than the max number of them
            camOutPath = os.path.join(config['outPath'], cam.name())
            camOutGlob = os.path.join(camOutPath, "*.jpg")
            files = glob.glob(camOutGlob)
            if len(files) > config['maxFrames']:
                files.sort()
                try:
                    if options.verbose > 2:
                        print("Removing file '{0}'".format(files[0]))
                    os.remove(files[0])
                except Exception:
                    print("FIXME")

            fPath = os.path.join(camOutPath, ts + ".jpg")
            with open(fPath, "w+") as f:
                if options.verbose > 2:
                    print("Writing frame to file '{0}'".format(fPath))
                f.write(img)
        if config['numFrames'] > 0:
            count += 1
            if count >= config['numFrames']:
                if options.verbose > 3:
                    print("Completed capture of {0} frames per camera".
                          format(count))
                break
        if options.verbose > 2:
            print("Delaying {0} secs".format(config['delay']))
            print("")
        time.sleep(config['delay'])

if __name__ == '__main__':
    main()
