"""
string_util.py
A sample module with utility functions for string manipulation
"""

def text_before(main_text, substring, flag_failure=False):
    """
    Get the text before a substring
    Args:
        text (str): The text to search
        substring (str): The substring to search for
        flag_failure (bool): If True, raise an error if the substring is not found
    Returns:
        cut_text: The text before the substring
    """
    # Find substring in main text
    index = main_text.find(substring)
    
    # If substring is found, return the text before it
    if index != -1:
        return main_text[:index]
    
    # If substring is not found, raise an error if flag_failure is True
    if flag_failure:
        raise ValueError(f"substring {substring} not found in text")
    
    # If substring is not found, return the entire text
    return main_text


def text_after(main_text,substring, flag_failure=False):
    """
    Get the text after a substring
    Args:
        text (str): The text to search
        substring (str): The substring to search for
        flag_failure (bool): If True, raise an error if the substring is not found
    Returns:
        cut_text: The text after the substring
    """
    index = main_text.find(substring)
    
    # If substring is found, return the text before it
    if index != -1:
        return main_text[index + len(substring):]
        
    # If substring is not found, raise an error if flag_failure is True
    if flag_failure:
        raise ValueError(f"substring {substring} not found in text")
    
    # If substring is not found, return the entire text
    return main_text

def text_between(main_text, start_substring, end_substring, flag_failure=False):
    """
    Get the text between two substrings
    Args:
        text (str): The text to search
        start_substring (str): The substring to search for at the beginning
        end_substring (str): The substring to search for at the end
        flag_failure (bool): If True, raise an error if the substring is not found
    Returns:
        cut_text: The text between the two substrings
    """
    # Find the start substring in the main text
    start_index = main_text.find(start_substring)
    
    # If start substring is found, find the end substring
    if start_index != -1:
        end_index = main_text.find(end_substring, start_index + len(start_substring))
        
        # If end substring is found, return the text between the two substrings
        if end_index != -1:
            return main_text[start_index + len(start_substring):end_index]
        
        # If end substring is not found, raise an error if flag_failure is True
        if flag_failure:
            raise ValueError(f"end substring {end_substring} not found in text")
    
    # If start substring is not found, raise an error if flag_failure is True
    if flag_failure:
        raise ValueError(f"start substring {start_substring} not found in text")
    
    # If start substring is not found, return the entire text
    return main_text

def text_excluding(main_text, substring, flag_failure=False):
    """
    Get the text excluding a substring
    Args:
        text (str): The text to search
        substring (str): The substring to search for
        flag_failure (bool): If True, raise an error if the substring is not found
    Returns:
        cut_text: The text excluding the substring
    """
    # Find substring in main text
    index = main_text.find(substring)
    
    # If substring is found, return the text excluding it
    if index != -1:
        return main_text[:index] + main_text[index + len(substring):]
    
    # If substring is not found, raise an error if flag_failure is True
    if flag_failure:
        raise ValueError(f"substring {substring} not found in text")
    
    # If substring is not found, return the entire text
    return main_text