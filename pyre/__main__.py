"""
Created on Sep 12, 2013

@author: u0490822
"""
import pyre.launcher as launcher


def main():
    # print(f"CWD: {os.getcwd()}")
    # print(f"Path: {sys.path}")
    launcher.build_container()
    launcher.Run()


if __name__ == '__main__':
    main()
