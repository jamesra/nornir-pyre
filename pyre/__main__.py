'''
Created on Sep 12, 2013

@author: u0490822
'''

import sys

#if not hasattr(sys, 'frozen'):
    #import wxversion
    #wxversion.select('2.8')

from pyre import state
from pyre import launcher

def main():
    state.init()
    launcher.Run()

if __name__ == '__main__':
    main()