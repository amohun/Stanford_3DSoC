import pdb
from os import getcwd
from sys import path
import sys

path.append(getcwd())
from SourceScripts import nirram_abstracted



def main():
    #pdb.set_trace()
    print(sys.argv)
    quit()
    settings = '.\\settings\\MPW_Direct_Write.toml'
    nirram = nirram_abstracted.NIRRAM()

if __name__ == '__main__':
    main()
