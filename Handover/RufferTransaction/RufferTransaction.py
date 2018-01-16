
import argparse
import csv
import os

parser = argparse.ArgumentParser()
parser.add_argument('--Input', help='pathname of input csv file')
parser.add_argument('--Output', help='pathname of output csv file (not used, for Gaspode only)')
parser.add_argument('--Temp', help='pathname used for output file location')

parser_warn = parser.add_mutually_exclusive_group(required=False)
parser_warn.add_argument('-warn', dest='warn', help='Display warnings (default)', action='store_true')
parser_warn.add_argument('-no-warn', dest='warn', help='Suppress warnings', action='store_false')
parser.set_defaults(warn=True)

args = parser.parse_args()
hash_file_name = os.path.basename(args.Input)

uscore_counter = 0
file_name = 'no name'
for index, character in enumerate(hash_file_name):
    if character == '_':
        uscore_counter += 1

    if uscore_counter == 2:
        file_name = hash_file_name[:index]
        break


if file_name != 'no name':
    input_file_name = file_name + '.csv'
    output_file_name = file_name + '_1.csv'
else:
    input_file_name = hash_file_name
    output_file_name = hash_file_name[:-4] + '_1' + hash_file_name[-4:]

# in file
in_csv_file = open(args.Input, 'r')

# out file
output_file = os.path.join(args.Temp, output_file_name)
out_csv_file = open(output_file, 'w')


# returns the indexs of all DOUBLE quotes in the input_row
def get_range(input_row):
    indexes = []
    my_index = 0
    start = 0
    while True:
        my_index = input_row.find("\"", start)
        # ends loop if no more single quotes
        if my_index == -1:
            break
        indexes.append(my_index)
        start = my_index + 1

    return indexes


def find_n_replace(input_row):

    # get affected ranges
    edit_range = get_range(input_row)
    instances = len(edit_range)

    for i in range(0, int(instances), 2):
        substring = input_row[edit_range[i]:edit_range[i+1]+1]
        substring = substring.replace(",", " ")
        substring = substring.replace("\"", "")

        input_row = input_row[:edit_range[i]] + substring + input_row[edit_range[i+1]+1:]

    return input_row


# copy csv to output file
for row in in_csv_file:
    row = find_n_replace(row)
    out_csv_file.write(row)

out_csv_file.close()
