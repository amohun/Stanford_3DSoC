import numpy as np
import timeit

numpy_array_total_time = []
list_total_time =[]
for i in range(1000):
    if i%100 == 0:
        print(i)
    # Example list of string variables representing integer values
    string_variables = ["wl" + str(i) for i in range(255)]

    # Extract integers from string variables using list comprehension
    integer_values = [int(variable[2:]) for variable in string_variables]

    # Time taken to create a regular Python list of integers
    list_time = timeit.timeit(lambda: [np.uint8(variable[2:]) for variable in string_variables], number=100)

    # Time taken to create a NumPy array with dtype uint8
    np_array_time = timeit.timeit(lambda: np.array([np.uint8(variable[2:]) for variable in string_variables]), number=100)

    np_array = np.array([np.uint8(variable[2:]) for variable in string_variables])
    list_array = [np.uint8(variable[2:]) for variable in string_variables]

    # Time taken to split NumPy array into two subarrays based on the condition
    np_operation_time = timeit.timeit(lambda: [np_array[np_array < 66], np_array[np_array >= 66]], number=100)
    print(np_array[np_array < 66])
    print(np_array[np_array >= 66])
    # Time taken to split list into two sublists based on the condition
    list_operation_time = timeit.timeit(lambda: [[val for val in list_array if val < 66], [val for val in list_array if val >= 66]], number=100)

    numpy_array_total_time.append(np_array_time + np_operation_time) 
    list_total_time.append(list_time + list_operation_time)


print(f"NumPy array: {np.average(numpy_array_total_time)}, {np.std(numpy_array_total_time)}")
print(f"List: {np.average(list_total_time)}, {np.std(list_total_time)}")
