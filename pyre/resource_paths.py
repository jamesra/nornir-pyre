import logging
import os

from pkg_resources import resource_filename


def ResourcePath() -> str:
    Logger = logging.getLogger("resources")
    rpath = resource_filename(__name__, "resources")
    # rpath = os.path.join(PackagePath(), 'resources')
    Logger.info('Resources path: ' + rpath)
    return rpath


def README() -> str:
    """Returns README.txt file as a string"""
    readmePath = resource_filename(__name__, 'README.txt')
    if not os.path.exists(readmePath):
        return "No readme.txt was found in " + readmePath

    with open(readmePath, 'r') as hReadme:
        readme = hReadme.read()
        hReadme.close()
        return readme
