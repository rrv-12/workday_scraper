# Workday Scraper

A Python tool for scraping Workday job postings.

## Prerequisites

- Python 3.x installed on your system
- VS Code (recommended)

## Setup Instructions

### 1. Create and Activate Virtual Environment

First, navigate to the project folder in VS Code terminal and create a virtual environment:

```bash
python -m venv venv
```

Then activate the virtual environment:

```bash
venv\Scripts\activate
```

### 2. Install Dependencies

Install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Initial Setup

Run the setup script to configure the application:

```bash
python setup.py
```

Follow the prompts to answer the configuration questions.

### 4. Run the Scraper

After completing the setup, run the scraper with the generated configuration:

```bash
python workday_scraper.py --config config.json
```

## Notes

- Make sure you are running all commands from the VS Code terminal with the project folder opened
- The virtual environment must be activated before running any Python commands
- The `config.json` file will be generated during the setup process
