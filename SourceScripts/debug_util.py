import inspect

class DebugUtil:
    def __init__(self, debug=False, record=False):
        self.debug = debug
        self.init_debug = debug
        self.record = record
        
    def set_debug(self, debug):
        if debug is not None:
            self.debug = debug
    
    def debug_message(self, message):
        if self.debug:
            if type(message) is list:
                for m in message:
                    print(m)
                return 0
            print(message)
        return 0
    
    def reset_debug(self):
        self.debug = self.init_debug

    def start_function_debug(self, debug=None):
        # Set the debug printout to the current debug value
        self.set_debug(debug)
        
        if self.debug:
            current_function = inspect.currentframe().f_back.f_code.co_name
            dash = "-" * len(current_function)
            print("\n\n--------", dash)
            print(f"Running {current_function}...")
            print(dash, "------\n")
    
    def operation_debug(self, internal, variables, values):
        if self.debug:
            print(f"{internal} variables: {variables}:\n")
            for variable, value in zip(variables, values):
                print(f"{variable}: {value}")
    
    def end_function_debug(self):
        if self.debug:
            current_function = inspect.currentframe().f_back.f_code.co_name
            print("\n\n ---------------------------------")
            print(f"Finished {current_function}...")
            print(" ---------------------------------\n")
        self.reset_debug()

# Example usage
class ExampleClass:
    def __init__(self):
        self.debug_util = DebugUtil(debug=True)

    def example_function(self):
        self.debug_util.start_function_debug()
        # Function logic here
        self.debug_util.operation_debug("Example", ["var1", "var2"], [1, 2])
        self.debug_util.end_function_debug()

if __name__ == "__main__":
    example = ExampleClass()
    example.example_function()
