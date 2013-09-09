'''
Created on Aug 30, 2013

@author: James Anderson
'''

from ez_setup import use_setuptools
from setuptools import setup, find_packages


import sys

if __name__ == '__main__':
    use_setuptools()

    data_files = []
    # data_files = {'pyre' : ['pyre/resources/*.png']}
    # data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]
    # data_files=matplotlib.get_py2exe_datafiles()
    # data_files.append(("Microsoft.VC90.CRT", ['msvcp90.dll']))
    # data_files.append(("", glob(r'*.png')))

    required_packages = ["numpy",
                         "scipy",
                         "matplotlib",
                         "pyglet",
                         "nornir_pools",
                         "nornir_shared",
                         "nornir_imageregistration",
                         "wx",
                         "wxversion"]

    dependency_links = ["git+http://github.com/jamesra/nornir-pools#egg=nornir_pools",
                        "git+http://github.com/jamesra/nornir-shared#egg=nornir_shared",
                        "git+http://github.com/jamesra/nornir-imageregistration#egg=nornir_imageregistration"]



    includes = []
    packages = ['pyre']


    # GUI applications require a different base on Windows (the default is for a
    # console application).
    base = None
    if sys.platform == "win32":
        base = "Win32GUI"

    # setup(data_files=data_files, console=['Pyre.py'])
    setup(name="pyre",
          version="1.0.0",
          data_files=data_files,
          description='Python Image Registration Tool',
          author='James Anderson and Drew Ferrell',
          author_email='james.r.anderson@utah.edu',
          console=['pyre.py'],
          required_packages=required_packages,
          dependency_links=dependency_links,
          package_data={'pyre' : ['resources/*.png']})