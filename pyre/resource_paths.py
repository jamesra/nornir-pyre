import logging
import os
import pyre


def ResourcePath() -> str:
    Logger = logging.getLogger("resources")
    rpath = os.path.join(pyre.__path__[0], 'resources')
    Logger.info('Resources path: ' + rpath)
    return rpath


def README() -> str:
    """Returns README.txt file as a string"""
    readmePath = os.path.join(pyre.__path__[0], 'README.txt')
    if not os.path.exists(readmePath):
        return "No readme.txt was found in " + readmePath

    with open(readmePath, 'r') as hReadme:
        readme = hReadme.read()
        hReadme.close()
        return readme
