# LGTVestra Python Script
maps transaction data in xml file to MIFID2 complient csv file

To run this script your machine will need to have python installed. 

To run this script, ensure both scripts (unavista_mifid2_wrapper.py & unavista_mifid2_xml2csv.py) are in the same directory. In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. just type C:\somepath\Documents\code\scriptfolder\myfile.csv. When you need to input a file path inside double quotes "[file path]" replace all single slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv". Following these rules type the following into the command line:

cd [directory of script]

py unavista_mifid2_wrapper.py --Input "[Input file path]" --Temp "[Output file directory]"

This script will automatically rename the file to 'python_processed_(yyyymmddhhmmss).py'

Note: if you are unsure whether you have python installed type the following into the command line: 

py -V

This will either output your version of python or give some error if you dont have it installed.

