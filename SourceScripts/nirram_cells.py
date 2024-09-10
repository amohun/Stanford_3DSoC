
class RRAMCells:
    def __init__(self,
                 cells: list,
                 wls: list,
                 bls: list,
                 bls_unsel:list,
                 bls_sel:list,
                 sls: list):

        self.cells = cells
        self.wls = wls
        self.bls = bls
        self.bls_unsel = bls_unsel
        self.bls_sel = bls_sel
        self.sls = sls
        
    def add_cells(self, cells=None, wls=None, bls=None):
        pass

    def remove_cells(self, cells=None, wls=None, bls=None):
        pass

    def add_wls(self, wls=None):
        pass

    def remove_wls(self, wls=None):
        pass

    def add_bls(self, bls=None):
        pass

    def remove_bls(self, bls=None):
        pass

    def check_if_cells_exist(self, cells=None,  wls=None, bls=None):
        pass

    # Add more methods as needed

if __name__ == "__main__":
    # Code to test the NirramCells class
    pass