import os
import subprocess
import sys
from datetime import datetime

def run_notebook(notebook_path):
    """Run a Jupyter notebook as a script"""
    print(f"Running notebook: {notebook_path}")
    
    # Use nbconvert to run the notebook
    result = subprocess.run(
        [
            "jupyter", "nbconvert", 
            "--to", "notebook", 
            "--execute", 
            "--output", notebook_path,
            notebook_path
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error running notebook: {result.stderr}")
        return False
    else:
        print(f"Notebook executed successfully")
        return True

def copy_html_to_docs():
    """Copy the latest HTML file to docs folder for GitHub Pages"""
    # Create docs folder if it doesn't exist
    os.makedirs("docs", exist_ok=True)
    os.makedirs("docs/history", exist_ok=True)
    
    # Find the latest HTML file in daily_html folder
    today = datetime.now().strftime('%Y-%m-%d')
    daily_html_folder = "daily_html"  # Update this if your HTML files are stored elsewhere
    today_file = os.path.join(daily_html_folder, f"{today}.html")
    
    if not os.path.exists(daily_html_folder):
        os.makedirs(daily_html_folder, exist_ok=True)
        print(f"Created directory: {daily_html_folder}")
        
    if not os.path.exists(today_file):
        print(f"HTML file for today ({today}) not found.")
        return False
    
    # Copy to docs folder
    try:
        # Read content
        with open(today_file, 'r', encoding='utf-8') as src:
            content = src.read()
        
        # Write to index.html
        with open("docs/index.html", 'w', encoding='utf-8') as dest:
            dest.write(content)
            
        # Write to history folder
        with open(f"docs/history/{today}.html", 'w', encoding='utf-8') as hist:
            hist.write(content)
            
        print(f"Successfully copied HTML files to docs folder")
        return True
    except Exception as e:
        print(f"Error copying files: {e}")
        return False

def push_to_github():
    """Push updates to GitHub"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Git commands
        commands = [
            ["git", "add", "docs/index.html", f"docs/history/{today}.html"],
            ["git", "commit", "-m", f"Update schedule for {today}"],
            ["git", "push"]
        ]
        
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error executing command {cmd}: {result.stderr}")
                return False
                
        print("Successfully pushed updates to GitHub")
        return True
    except Exception as e:
        print(f"Error during git operations: {e}")
        return False

def main():
    """Main function to run daily update process"""
    print(f"Starting daily update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Run the notebook that generates HTML files
    if not run_notebook("LaFermedelaCour-Résumé.ipynb"):
        print("Failed to run HTML generation notebook. Exiting.")
        return
    
    # Step 2: Copy generated HTML to docs folder
    if not copy_html_to_docs():
        print("Failed to copy HTML files. Exiting.")
        return
    
    # Step 3: Push changes to GitHub
    if not push_to_github():
        print("Failed to push changes to GitHub. Exiting.")
        return
    
    print(f"Daily update completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()