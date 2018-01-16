# Banco do brasil
maps transaction data from an xml file to a MIFID2 complient csv file

To run this script your machine will need to have python installed. 

To run this script, ensure both scripts (banco_wrapper.py & banco_xml2csv.py) are in the same directory. In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. just type C:\somepath\Documents\code\scriptfolder\myfile.csv. When you need to input a file path inside double quotes "[file path]" replace all single slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv". Following these rules type the following into the command line:

cd [directory of script]

py banco_wrapper.py --Input "[Input file path]" --Temp "[Output file directory]"

This script will take the name the output file depending on the Temp input

Note: if you are unsure whether you have python installed type the following into the command line: 

py -V

This will either output your version of python or give some error if you dont have it installed.