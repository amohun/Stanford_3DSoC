import csv
import datetime

def update_data_log(date, time, filename, location, notes, test_log_path="test_log.csv"):
    """
    Update the CSV with information on what files were written to,
    what information they contained, and where they are stored.
    The function then returns an incrementing identifier (####)
    that resets each day.
    """

    # Read the last row of the CSV file to get the last identifier
    last_hash = "0000"
    try:
        with open(test_log_path, "r") as test_log:
            reader = csv.reader(test_log)
            last_row = list(reader)[-1]  # Get the last row
            last_date = last_row[0]  # Get the date from the last row
            if last_date == date:  # Check if the last date matches the current date
                last_hash = str(int(last_row[4]) + 1).zfill(4)  # Increment the last identifier by 1
    except FileNotFoundError:
        # If the file doesn't exist, this is the first entry of the day
        pass

    # Write the new row with the updated identifier
    with open(test_log_path, "a", newline="") as test_log:
        writer = csv.writer(test_log)
        writer.writerow([date, time, filename, location, last_hash, notes])

    # Return the updated identifier
    return last_hash

def main():
    # Get the current date and time
    current_date = datetime.date.today().strftime("%Y-%m-%d")
    current_time = datetime.datetime.now().strftime("%H:%M:%S")

    # Example file information
    filename = "test_file.txt"
    location = "test_location"
    notes = "test_notes"

    # Call the update_data_log function
    hash_number = update_data_log(current_date, current_time, filename, location, notes)
    print("Updated identifier:", hash_number)

if __name__ == "__main__":
    main()
