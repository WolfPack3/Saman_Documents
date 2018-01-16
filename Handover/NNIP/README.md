# xml_csv_convert
maps transaction data in xml file to MIFID2 complient csv file

To run this script your machine will need to have python installed and the python library numpy. 

To run this script, ensure both scripts are in the same directory. In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. C:\somepath\Documents\code\scriptfolder\myfile.csv. When you input a file path inside double quotes "[file path]" replace all slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv" 

Following the above rules type the following into the command line:

cd [directory of script]

py xml2csv_wrapper.py --Input "[Input file path]" --Temp "[Output file directory]"

This script will automatically rename the file in the following format:
"LEI_MIFID_yyyymmdd_hhmmss_NNIPOUTPUT_0001.csv"

Note: if you are unsure whether you have python installed type the following into the command line: 

py -V

This will either output your version of python or give an error if it doesnt exist. If you dont have the numpy library installed you can install it by typying the following into the command line:

py -m pip install numpy

