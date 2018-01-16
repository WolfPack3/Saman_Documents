
import argparse
import csv
import os
import numpy as np
import time

start_time = time.time()

parser = argparse.ArgumentParser()
parser.add_argument('-in-csv', help='name of input csv file')
parser.add_argument('-ref-data', help='name of reference data')
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
def strip_outer_spaces(string):
    indexs = get_firstlast_index(string)
    if len(indexs) == 2:
        first_index = indexs[0]
        last_index = indexs[1]
        substring = string[first_index:last_index]
        return substring
    else:
        return string.strip()


# runs strip outer spaces for a whole row
def strip_row(row):
    for index, entry in enumerate(row):
        row[index] = strip_outer_spaces(entry)
    return row


# filter rekeningid
def filter_rekeningid(ref_reader, in_reader):
    refdata_list = list(ref_reader)
    refdata_nplist = np.array(refdata_list)
    rekeningid_column = refdata_nplist[:, 50]

    new_column = np.unique(rekeningid_column)

    input_counter = 0
    output_counter = 1
    for row in in_reader:
        input_counter += 1

        if input_counter == 1:
            outfile_writer.writerow(row)
            continue

        rekeningid = strip_outer_spaces(row[2])
        bool_array = new_column == rekeningid
        id_in_refdata = np.any(bool_array)

        if id_in_refdata:
            output_counter += 1
            outfile_writer.writerow(strip_row(row))

    print('{0} out of the {1} rows have been kept'.format(output_counter, input_counter))
    return


input_file_path = os.path.join(os.getcwd(), 'In', args.in_csv)
output_file_path = os.path.join(os.getcwd(), 'Out', 'OUTPUT_' + args.in_csv)
refdata_file_path = os.path.join(os.getcwd(), 'Ref_Data', args.ref_data)

# in file
in_csv_file = open(input_file_path, 'r')
infile_reader = csv.reader(in_csv_file, delimiter=';')
# out file
out_csv_file = open(output_file_path, 'w', newline='')
outfile_writer = csv.writer(out_csv_file, delimiter=';')
# ref data
ref_data_file = open(refdata_file_path, 'r')
refdata_reader = csv.reader(ref_data_file, delimiter=';')

# run filter function
filter_rekeningid(refdata_reader, infile_reader)

out_csv_file.close()
in_csv_file.close()
ref_data_file.close()

end_time = time.time()
time_diff = end_time - start_time
print('The code took {0} seconds'.format(round(time_diff)))

