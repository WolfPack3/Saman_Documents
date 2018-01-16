
import argparse
import csv
import os

parser = argparse.ArgumentParser()
parser.add_argument('-in-csv', help='pathname of input csv file')
parser.add_argument('-out-csv', help='pathname of output csv file')
args = parser.parse_args()


# get the index of the first and last none space character
def get_firstlast_index(a_string):
    first_last = []

    # get index of first character
    for index, letter in enumerate(a_string):
        if letter != ' ':
            first_last.append(index)
            break
    # get index of last character
    for index, letter in reversed(list(enumerate(a_string))):
        if letter != ' ':
            first_last.append(index+1)
            break

    return first_last


# remove spaces from start and end of text
def strip_value(string):
    indexs = get_firstlast_index(string)
    if len(indexs) == 2:
        first_index = indexs[0]
        last_index = indexs[1]
        substring = string[first_index:last_index]
        return substring
    else:
        return string.strip()


# remove value if not O or F
def keep_O_F(ordersoort):
    if ordersoort != 'O' and ordersoort != 'F':
        return True
    else:
        return False


# in file
in_csv_file = open(args.in_csv, 'r')
reader_obj = csv.reader(in_csv_file, delimiter=';')
# out file
out_csv_file = open(args.in_csv, 'w', newline='')
writer_obj = csv.writer(out_csv_file, delimiter=';')

for counter, row in enumerate(reader_obj):
    if keep_O_F(row[14]):
        continue
    for index, entry in enumerate(row):
        row[index] = strip_value(entry)

    writer_obj.writerow(row)

out_csv_file.close()
in_csv_file.close()
