from digital_pattern import DigitalPattern
from excel_arbitrary_data import ExcelInterface
from masks import Masks
from nirram_abstracted import NIRRAM
import numpy

def main():
    test_pattern = ExcelInterface('ArbitraryTestbench.xlsx')
    signal_rows = test_pattern.get_rows_between_keyword_and_empty('Arbitrary Waveforms')
    signals = test_pattern.rows_to_dict(signal_rows[0], signal_rows[1]+1,1)
    print(signals)

if __name__ == '__main__':
    main()
