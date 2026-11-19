# Simple Data Analysis Sales (`SimpleDataAnalysisSales`)

An application for cleaning, processing, and analyzing sales, product, purchase, and stock datasets. It includes an interactive graphical interface (`gui_app.py`), a full end-to-end pipeline script (`all_steps.py`), OS launcher scripts for Windows and Unix-like systems, and Docker container support.

- **GitHub Repository**: [https://github.com/n12iki/SimpleDataAnalysisSales](https://github.com/n12iki/SimpleDataAnalysisSales)

---

## Table of Contents

1. [How Everything Works](#1-how-everything-works)
2. [Project Structure](#2-project-structure)
3. [Step-by-Step Setup: Running Python Directly](#3-step-by-step-setup-running-python-directly)
4. [Step-by-Step Setup: Running with Docker Only](#4-step-by-step-setup-running-with-docker-only)
5. [Step-by-Step: Preparing Your Data](#5-step-by-step-preparing-your-data)
6. [Step-by-Step: Running the Application & Pipeline](#6-step-by-step-running-the-application--pipeline)
7. [Step-by-Step: Creating a Desktop Shortcut (Windows)](#7-step-by-step-creating-a-desktop-shortcut-windows)
8. [Step-by-Step: Stopping the Application](#8-step-by-step-stopping-the-application)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. How Everything Works

The application follows a modular data-processing architecture:

1. **Input Data (`data/`)**:
   * Raw datasets (products, purchases, sales, and stock) are stored inside the `data/` directory (kept in Git via `data/.gitkeep`).
2. **Data Cleaning Layer (`cleaning/`)**:
   * `cleaning/data_cleaning.py`: Shared cleaning utilities, formatting rules, and helper functions used across modules.
   * `cleaning/product_clean.py`: Cleans and standardizes product records.
   * `cleaning/purchase_clean.py`: Cleans and standardizes purchase records.
   * `cleaning/sales_clean.py`: Cleans and standardizes sales transaction records.
   * `cleaning/stock_clean.py`: Cleans and standardizes stock/inventory records.
3. **Analysis Layer (`analysis/`)**:
   * `analysis/sales_analysis.py`: Consumes cleaned datasets to compute metrics, run sales analysis, and generate outputs/reports.
4. **Execution Entry Points**:
   * `all_steps.py`: Runs the complete sequence of cleaning and analysis steps automatically from start to finish.
   * `gui_app.py`: Launches the graphical user interface so you can interact with the pipeline, data, and analysis visually.
5. **Launcher & Container Helpers**:
   * **Windows**: `Launch Sales Analysis.bat`, `Stop Sales Analysis.bat`, `Create Desktop Shortcut.bat`, and `Create Desktop Shortcut.ps1` (with icon `assets/sales-analysis.ico`).
   * **macOS / Linux**: `launch.sh`.
   * **Docker**: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `docker/start.sh`, and `docker/fonts.conf`.

---

## 2. Project Structure

```text
SimpleDataAnalysisSales/
├── .dockerignore                  # Files excluded from Docker build context
├── .gitattributes                 # Git line-ending and file attributes
├── Create Desktop Shortcut.bat    # Windows wrapper to create a desktop shortcut
├── Create Desktop Shortcut.ps1    # PowerShell script that builds the shortcut
├── Dockerfile                     # Instructions to build the Docker image
├── Launch Sales Analysis.bat      # Windows script to start the application
├── README.md                      # Project documentation
├── Stop Sales Analysis.bat        # Windows script to stop the application
├── all_steps.py                   # Script that runs all pipeline steps in order
├── analysis/
│   ├── __init__.py
│   └── sales_analysis.py          # Core sales analysis and reporting module
├── assets/
│   └── sales-analysis.ico         # Windows desktop shortcut icon
├── cleaning/
│   ├── __init__.py
│   ├── data_cleaning.py           # Common cleaning helpers
│   ├── product_clean.py           # Product data cleaner
│   ├── purchase_clean.py          # Purchase data cleaner
│   ├── sales_clean.py             # Sales data cleaner
│   └── stock_clean.py             # Stock/inventory data cleaner
├── data/
│   └── .gitkeep                   # Directory for input/output data files
├── docker/
│   ├── fonts.conf                 # Font configuration inside Docker
│   └── start.sh                   # Startup script inside Docker
├── docker-compose.yml             # Docker Compose service definition
├── gui_app.py                     # Graphical User Interface (GUI)
├── launch.sh                      # Unix/Linux/macOS launch script
└── requirements.txt               # Python dependencies list
```

---

## 3. Step-by-Step Setup: Running Python Directly

Follow these steps if you want to run the Python scripts and GUI directly on your computer without Docker.

### Step 1: Download and Install Git
1. Go to [https://git-scm.com/](https://git-scm.com/) and download **Git** for your operating system (or download the repository directly from GitHub).
2. Install Git using the default options and verify it in a terminal:
   ```bash
   git --version
   ```

### Step 2: Download and Install Python 3
1. Go to [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Download and run the latest **Python 3** installer for your OS.
3. **Important (Windows)**: Check the box **"Add python.exe to PATH"** before clicking **Install Now**.
4. Verify Python and `pip` are working:
   ```bash
   python --version
   pip --version
   ```
   *(On macOS/Linux, use `python3` and `pip3` if `python` is not mapped to Python 3.)*

### Step 3: Clone the GitHub Repository
1. Open **Command Prompt**, **PowerShell**, or **Terminal**.
2. Navigate to the folder where you want to store the project, then clone the repository:
   ```bash
   git clone https://github.com/n12iki/SimpleDataAnalysisSales.git
   cd SimpleDataAnalysisSales
   ```

### Step 4: Create and Activate a Python Virtual Environment
Creating a virtual environment isolates project dependencies from the rest of your system:

* **On Windows (Command Prompt)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```
* **On Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
* **On macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### Step 5: Install Required Python Dependencies
With `.venv` activated, upgrade `pip` and install everything in `requirements.txt`:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 6: Make the Shell Launcher Executable (macOS / Linux Only)
```bash
chmod +x launch.sh
```

---

## 4. Step-by-Step Setup: Running with Docker Only

Follow these steps if you do **not** want to set up Python or install Python packages locally and only want to run the application inside Docker.

### Step 1: Download and Install Docker
1. Go to [https://www.docker.com/get-started/](https://www.docker.com/get-started/).
2. Download and install **Docker Desktop** (for Windows or macOS) or **Docker Engine + Docker Compose** (for Linux).
3. Launch Docker Desktop and wait until the Docker engine status shows as running.
4. Verify Docker and Docker Compose in a terminal:
   ```bash
   docker --version
   docker compose version
   ```

### Step 2: Clone the GitHub Repository
1. Open a terminal and clone the project from GitHub:
   ```bash
   git clone https://github.com/n12iki/SimpleDataAnalysisSales.git
   cd SimpleDataAnalysisSales
   ```

### Step 3: Place Your Input Data in `data/`
1. Copy your input dataset files into the `data/` folder inside `SimpleDataAnalysisSales/` before starting the container so Docker can access them as configured in `docker-compose.yml`.

### Step 4: Build and Start the Docker Container
1. Run Docker Compose from the `SimpleDataAnalysisSales` root directory (this builds the image using `Dockerfile`, `.dockerignore`, `docker/fonts.conf`, and `docker/start.sh`):
   ```bash
   docker compose up --build
   ```
2. *(Optional)* To run the container in the background (detached mode):
   ```bash
   docker compose up --build -d
   ```
3. *(Optional)* To monitor container output logs:
   ```bash
   docker compose logs -f
   ```

---

## 5. Step-by-Step: Preparing Your Data

1. Open the `data/` folder inside `SimpleDataAnalysisSales/`.
2. Copy your raw input files into `data/` (covering products, purchases, sales, and stock as required by the cleaning scripts in `cleaning/`).
3. Make sure none of the input files are currently open/locked in Excel or another spreadsheet editor before running the cleaning or analysis scripts.

---

## 6. Step-by-Step: Running the Application & Pipeline

### Method A: Run the Graphical Interface (`gui_app.py`)
* **Windows (One-Click)**:
  1. Double-click **`Launch Sales Analysis.bat`** in File Explorer (or run it from Command Prompt).
* **macOS / Linux (Shell Script)**:
  1. In the project root directory, run:
     ```bash
     ./launch.sh
     ```
* **Any OS (Direct Python Command)**:
  1. Ensure your virtual environment (`.venv`) is activated.
  2. Run:
     ```bash
     python gui_app.py
     ```

### Method B: Run the Full Automated Pipeline (`all_steps.py`)
To execute all cleaning and analysis steps sequentially without opening the GUI:
1. Open a terminal in `SimpleDataAnalysisSales/` and activate `.venv`.
2. Run:
   ```bash
   python all_steps.py
   ```

### Method C: Run Individual Cleaning or Analysis Modules
If you want to run a specific step independently:
1. Activate `.venv` in `SimpleDataAnalysisSales/`.
2. Run the desired module:
   ```bash
   python cleaning/product_clean.py
   python cleaning/purchase_clean.py
   python cleaning/sales_clean.py
   python cleaning/stock_clean.py
   python analysis/sales_analysis.py
   ```

---

## 7. Step-by-Step: Creating a Desktop Shortcut (Windows)

1. Open the `SimpleDataAnalysisSales` folder in **File Explorer**.
2. Double-click **`Create Desktop Shortcut.bat`** (this invokes `Create Desktop Shortcut.ps1` and assigns `assets/sales-analysis.ico`).
3. A **Sales Analysis** shortcut will appear on your Windows Desktop for one-click launching.

---

## 8. Step-by-Step: Stopping the Application

* **Windows (Local)**:
  * Close the GUI window, or double-click **`Stop Sales Analysis.bat`** to terminate running app processes.
* **macOS / Linux (Local)**:
  * Close the GUI window, or press `Ctrl + C` in the terminal where `./launch.sh` or `gui_app.py` is running.
* **Docker**:
  * In the `SimpleDataAnalysisSales/` directory, run:
    ```bash
    docker compose down
    ```

---

## 9. Troubleshooting

* **`git` or `python` is not recognized**: Reinstall Git or Python 3 and ensure their installation directories are added to your system `PATH` (on Windows, check **"Add python.exe to PATH"** during Python setup).
* **`ModuleNotFoundError` when running Python scripts**: Make sure your `.venv` virtual environment is activated and re-run `pip install -r requirements.txt`.
* **PowerShell blocks `.venv\Scripts\Activate.ps1` or `Create Desktop Shortcut.ps1`**: Open PowerShell and allow local scripts for your user account:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
* **Permission denied on `launch.sh` (macOS/Linux)**: Run `chmod +x launch.sh` and execute `./launch.sh` again.
* **File not found or permission denied on data files**: Verify your datasets are inside `data/` and are not currently open in Excel or another program.
* **Docker build or startup issues**: Ensure Docker Desktop / Docker Engine is running, then inspect `docker-compose.yml`, `Dockerfile`, `docker/start.sh`, and `docker/fonts.conf`.