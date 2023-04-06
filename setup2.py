# from distutils.core import setup

from distutils.core import setup
from glob import glob
import sys

import matplotlib
import scipy

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

# from cx_Freeze import setup, Executable
if not hasattr(sys, 'frozen'):
    import wxversion

    wxversion.select('2.8')

# import py2exe
# import PyreGui

data_files = []
# data_files = {'pyre' : ['pyre/resources/*.png']}
# data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]     
# data_files=matplotlib.get_py2exe_datafiles()
# data_files.append(("Microsoft.VC90.CRT", ['msvcp90.dll']))
# data_files.append(("", glob(r'*.png')))

excludes = ["Tkconstants", "Tkinter", "tcl", '_gtkagg', '_tkagg']
includes = [
    r'matplotlib',
    r'numpy',
    r'scipy',
    r'pyglet',
    'wxversion',
    r'wx',
    'scipy.special._cephes',
    'scipy.special.orthogonal_eval',
    'scipy.special._logit',
    'scipy.special.add_newdocs',
    'scipy.linalg.fblas',
    'scipy.linalg.flapack',
    'scipy.linalg.clapack',
    'scipy.linalg.cblas',
    'scipy.sparse.csgraph',
    'scipy.sparse.csgraph._validation',
    'nornir_imageregistration',
    'nornir_shared',
    'nornir_pools',
    'sys']

includes = []
packages = ['pyre']

build_exe_options = {"packages": packages,
                     "excludes": excludes,
                     "includes": includes}

# GUI applications require a different base on Windows (the default is for a
# console application).
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# setup(data_files=data_files, console=['Pyre.py'])
setup(name="pyre",
      version="1.5.0",
      data_files=data_files,
      description='Python Image Registration Tool',
      author='James Anderson and Drew Ferrell',
      author_email='james.r.anderson@utah.edu',
      console=['pyre.py'],
      requires=includes,
      packages=packages,
      package_data={'pyre': ['resources/*.png']},
      options={
          'py2exe': {'excludes': excludes,
                     'includes': includes},
          "build_exe": build_exe_options})

#      executables = [Executable("Pyre.py", base=base)])
