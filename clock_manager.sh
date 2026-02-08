#!/bin/bash

# --- 1. Check for Python 3 ---
if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed. Please install Python 3 and try again."
    exit
fi

# --- 2. Setup Virtual Environment (Portability) ---
# This creates a folder to hold libraries so they don't
# affect the user's main Python installation.
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# --- 3. Activate Virtual Environment ---
source venv/bin/activate

# --- 4. Install Dependencies ---
echo "Installing dependencies..."
pip install --upgrade pip
pip install PyQt6 requests pytz adhanpy pygame macos-notifications

# --- 5. Run the Application ---
echo "Starting Adhan Clock..."
python3 gui_clock.py