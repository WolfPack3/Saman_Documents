# RekeningID
Compares the rekeningID's in the input file to reference data, if the input file ID is not present in the ref data exclude that row.

To run this script your machine will need to have python installed and the python library numpy. 

To run this script, ensure both scripts are in the same directory. In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. C:\somepath\Documents\code\scriptfolder\myfile.csv. When you input a file path inside double quotes "[file path]" replace all slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv" 

Following the above rules type the following into the command line:

cd [directory of script]

py RekeningID.py -in-csv "[Input file path]" -ref-data "[Ref data file path]"

This script will automatically rename the output file to the same as the input file with 'OUTPUT_' added to the beginning

Note: if you are unsure whether you have python installed type the following into the command line: 

py -V

This will either output your version of python or give an error if it doesnt exist. If you dont have the numpy library installed you can install it by typying the following into the command line:

py -m pip install numpy


# SpaceRemoval
Removes all spaces before the first and after the last characters in a a csv.

To run this script your machine will need to have python installed and the python library numpy. 

In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. C:\somepath\Documents\code\scriptfolder\myfile.csv. When you input a file path inside double quotes "[file path]" replace all slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv" 

Following the above rules type the following into the command line:

cd [directory of script]

py SpaceRemoval.py -in-csv "[Input file path]" -out-csv "[Output file path]"


