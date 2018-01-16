# RufferTransaction
Ensures a delimited file is correctly represented in a csv i.e. commas within quotes are not treated as delimiters.

To run this script your machine will need to have python installed. 

In the instructions below when you see a line break press the enter/return key. when you see [some file path] do not include the square brackets [], e.g. C:\somepath\Documents\code\scriptfolder\myfile.csv. When you input a file path inside double quotes "[file path]" replace all slashes '\\' with double slashes '\\\\' e.g. "C:\\\\somepath\\\\Documents\\\\code\\\\scriptfolder\\\\myfile.csv" 

Following the above rules type the following into the command line:

cd [directory of script]

py RufferTransaction.py --Input "[Input file path]" --Temp "[Output file directory]"

This script will automatically rename the file by adding '_1' to the end (but before the hash if there is one)

Note: if you are unsure whether you have python installed type the following into the command line: 

py -V

This will either output your version of python or give an error if it doesnt exist.

