'''
Created on Aug 30, 2013

@author: James Anderson
'''

import sys

from ez_setup import use_setuptools
from setuptools import setup, find_packages

if __name__ == '__main__':
    use_setuptools()

    data_files = []
    # data_files = {'pyre' : ['pyre/resources/*.png']}
    # data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]
    # data_files=matplotlib.get_py2exe_datafiles()
    # data_files.append(("Microsoft.VC90.CRT", ['msvcp90.dll']))
    # data_files.append(("", glob(r'*.png')))
    
    # OK to use pools v1.3.1, no changes made for v1.3.2

    required_packages = ["numpy>=1.8",
                         "scipy>=0.13.2",
                         "matplotlib",
                         "pyglet",
                         "nornir_pools>=1.3.1",
                         "nornir_shared>=1.3.2",
                         "nornir_imageregistration>=1.3.2",
                         "PyOpenGL>=3.0",
                         "pillow>=2.3"]

    dependency_links = ["git+http://github.com/jamesra/nornir-pools#egg=nornir_pools-1.3.1",
                        "git+http://github.com/jamesra/nornir-shared#egg=nornir_shared-1.3.2",
                        "git+http://github.com/jamesra/nornir-imageregistration#egg=nornir_imageregistration-1.3.2"]

    includes = []
    packages = find_packages()

    # GUI applications require a different base on Windows (the default is for a
    # console application).
    base = None
    if sys.platform == "win32":
        base = "Win32GUI"

    entry_points = {'gui_scripts' : ['pyre = pyre.__main__:main']}

    # setup(data_files=data_files, console=['Pyre.py'])
    setup(name="pyre",
          version="1.3.2",
          entry_points=entry_points,
          data_files=data_files,
          description='Python Image Registration Tool',
          author='James Anderson and Drew Ferrell',
          author_email='james.r.anderson@utah.edu',
          install_requires=required_packages,
          dependency_links=dependency_links,
          packages=packages,
          package_data={'pyre' : ['resources/*.png', 'README.txt']})
