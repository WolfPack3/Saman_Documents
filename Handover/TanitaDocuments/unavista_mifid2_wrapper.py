"""
unavista_mifid2_convert.py

Front-end for use by Gaspode in processing UnaVista MIFID 2 input XML files

Command line usage is as follows:

    python unavista_mifid2_convert.py ( followed by command options plus arguments as follows ..)

in which command options & their corresponding arguments are as follows:

    * --Input {path}

           Pathname of input file to process  (for use with Gaspode)

    * --Output {path}

        Pathname of input file to process  (for use with Gaspode)
        (specified by Gaspode, but not used by us or any of the scripts)

    * --Temp {path}

        Pathname of Temporary output file
        (specified by Gaspode, & directory part used by script

The script simply runs the unavista_mifid2_xml2csv.py script with suitable command options & arguments.
"""

import os
import argparse
import re
import sys

sys.path.append('.')

parser = argparse.ArgumentParser(description="UnaVista MIFID 2 master script used by Gaspode")

parser.add_argument('--Input',  help='Filename of Input XML file (specified by Gaspode)')
parser.add_argument('--Output', help='Leave blank, (specified by Gaspode)')
parser.add_argument('--Temp',   help='Output file directory, path used by Gaspode')

args = parser.parse_args()


def run_os_command(cmd_line):

    print(cmd_line + "\r\n")

    try:
        os.system('"' + cmd_line + '"')

    except Exception as e:
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)

        exit(-1)


# python executable path
python_path = sys.executable

# script_dir
script_dir = os.path.dirname(sys.argv[0])
script_path = os.path.join(script_dir, 'unavista_mifid2_xml2csv.py')

mm = re.match(r'(.*)\.xml', args.Input)
if mm is None:
    print('Input file "' + path_in_xml + '" is not an XML file!')
    exit(1)

path_temp = args.Temp if re.match(r'.*\.csv$', args.Temp) is None else os.path.dirname(args.Temp)

run_os_command('"' + python_path + '" "' + script_path + '" -in-xml "' + args.Input
               + '" -out-csv "' + args.Temp)

print("exiting unavista_mifid2_convert.py (after running unavista_mifid2_xml2csv.py) ..")
exit(0)


