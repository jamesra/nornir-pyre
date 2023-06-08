'''
Created on Sep 12, 2013

@author: u0490822
'''

import sys
import os

import pyre
from pyre import state
from pyre import launcher


def main():
    #print(f"CWD: {os.getcwd()}")
    #print(f"Path: {sys.path}")
    state.init()
    launcher.Run()


if __name__ == '__main__':
    main()
