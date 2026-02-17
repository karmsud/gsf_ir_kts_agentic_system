#!/usr/bin/env python3
"""
showTime.py - A simple script to display the current time
"""

import datetime

def show_current_time():
    """Display the current time in a formatted way"""
    
    # Get current time
    now = datetime.datetime.now()
    
    # Display current time information
    print("=" * 40)
    print("        CURRENT TIME DISPLAY")
    print("=" * 40)
    
    # Main time display
    print(f"Current Date & Time: {now.strftime('%A, %B %d, %Y')}")
    print(f"Time: {now.strftime('%I:%M:%S %p')}")
    print(f"24-hour format: {now.strftime('%H:%M:%S')}")
    
    print("-" * 40)
    
    # Additional formats
    print(f"Short format: {now.strftime('%m/%d/%Y %H:%M')}")
    print(f"ISO format: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("=" * 40)

if __name__ == "__main__":
    show_current_time()