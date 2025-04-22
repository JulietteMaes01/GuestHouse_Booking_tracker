import os
import subprocess
import schedule
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# Configuration - Update these values
# Configuration - Update these values
GOOGLE_CREDENTIALS_FILE = "google-credentials.json"
SPREADSHEET_NAME = "LaFermedelaCour_bookings.xsx"  # The exact name of your sheet
HTML_OUTPUT_DIR = "daily_html"
GITHUB_REPO_PATH = "."  # Current directory

def get_bookings_from_gsheet():
    """Get booking data from Google Sheet"""
    # Define the scope
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    # Authenticate
    credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    client = gspread.authorize(credentials)
    
    # Open the spreadsheet
    sheet = client.open(SPREADSHEET_NAME).sheet1
    
    # Get all data
    data = sheet.get_all_records()
    
    # Convert to pandas DataFrame
    df = pd.DataFrame(data)
    
    return df

def create_daily_html():
    """Create daily HTML file based on Google Sheet data"""
    # Make sure output directory exists
    os.makedirs(HTML_OUTPUT_DIR, exist_ok=True)
    
    # Get booking data
    df = get_bookings_from_gsheet()
    
    # Convert date columns to datetime if they're not already
    date_columns = ['arrival_date', 'departure_date']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    
    # Process for today
    today = datetime.now().date()
    
    # Find bookings active today
    today_bookings = df[(df['arrival_date'].dt.date <= today) & 
                         (df['departure_date'].dt.date >= today) &
                         (df['status'] != 'cancelled')]
    
    # Create HTML content
    if len(today_bookings) == 0:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Aujourd'hui à La Ferme de la Cour</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                h1 { color: #4CAF50; }
                .message { font-size: 24px; text-align: center; margin-top: 100px; }
            </style>
        </head>
        <body>
            <h1>La Ferme de la Cour - {date}</h1>
            <div class="message">
                <p>Aujourd'hui c'est repos! 😊</p>
            </div>
        </body>
        </html>
        """.format(date=today.strftime('%d/%m/%Y'))
    else:
        # Start HTML content
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Aujourd'hui à La Ferme de la Cour</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                h1 { color: #4CAF50; }
                .booking { border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; border-radius: 5px; }
                .arrival { background-color: #e6f7ff; }
                .departure { background-color: #fff2e6; }
                .both { background-color: #e6ffe6; }
                .regular { background-color: #f9f9f9; }
                .booking-title { font-weight: bold; margin-bottom: 10px; }
                .booking-info { margin-left: 15px; }
                .action-needed { color: #d9534f; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>La Ferme de la Cour - {date}</h1>
        """.format(date=today.strftime('%d/%m/%Y'))
        
        # Process each booking
        for _, booking in today_bookings.iterrows():
            arrival_date = booking['arrival_date'].date()
            departure_date = booking['departure_date'].date()
            
            # Determine booking type for styling
            if arrival_date == today and departure_date == today:
                booking_type = "both"
                special_message = "<p class='action-needed'>Préparer et nettoyer la chambre pour une réservation d'un jour.</p>"
            elif arrival_date == today:
                booking_type = "arrival"
                special_message = "<p class='action-needed'>Préparer la chambre pour l'arrivée des invités.</p>"
            elif departure_date == today:
                booking_type = "departure"
                special_message = "<p class='action-needed'>C'est leur dernier jour chez nous. Prévoir le nettoyage de la chambre.</p>"
            else:
                booking_type = "regular"
                special_message = ""
            
            # Check if it's a repeat guest
            repeat_guest_info = ""
            if booking.get('is_repeat_guest', False):
                repeat_guest_info = f"""
                <p><strong>Client fidèle!</strong></p>
                <p>Notes de la visite précédente: {booking.get('previous_stay_notes', 'Aucune note disponible')}</p>
                """
            
            # Add booking to HTML
            html_content += f"""
            <div class="booking {booking_type}">
                <div class="booking-title">{booking.get('room_name', 'Chambre')} - {booking.get('guest_name', 'Invité')}</div>
                <div class="booking-info">
                    <p>Séjour: {arrival_date.strftime('%d/%m/%Y')} au {departure_date.strftime('%d/%m/%Y')}</p>
                    <p>Contact: {booking.get('guest_phone', 'Non disponible')}</p>
                    <p>Origine de la réservation: {booking.get('booking_type', 'Non spécifié')}</p>
                    {repeat_guest_info}
                    {special_message}
                </div>
            </div>
            """
        
        # Close HTML content
        html_content += """
        </body>
        </html>
        """
    
    # Save HTML file
    file_path = os.path.join(HTML_OUTPUT_DIR, f"{today.strftime('%Y-%m-%d')}.html")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Generated HTML file for {today.strftime('%Y-%m-%d')}")
    return file_path

def push_to_github(html_file):
    """Push the HTML file to GitHub Pages"""
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Copy the file to the GitHub repository
    # Copy the file to the GitHub repository
    dest_file = os.path.join(GITHUB_REPO_PATH, "docs", "index.html")  # Main page always shows today's schedule
    history_file = os.path.join(GITHUB_REPO_PATH, "docs/history", f"{today}.html")  # Archive copy

    # Ensure history directory exists
    os.makedirs(os.path.join(GITHUB_REPO_PATH, "docs/history"), exist_ok=True)
    
    # Copy files
    try:
        with open(html_file, 'r', encoding='utf-8') as src:
            content = src.read()
            
        with open(dest_file, 'w', encoding='utf-8') as dest:
            dest.write(content)
            
        with open(history_file, 'w', encoding='utf-8') as hist:
            hist.write(content)
            
        # Git commands to commit and push
        os.chdir(GITHUB_REPO_PATH)
        subprocess.run(["git", "add", "docs/index.html", f"docs/history/{today}.html"])
        subprocess.run(["git", "commit", "-m", f"Update schedule for {today}"])
        subprocess.run(["git", "push"])
        
        print(f"Successfully pushed today's schedule to GitHub Pages")
        
    except Exception as e:
        print(f"Error updating GitHub repository: {e}")

def daily_update():
    """Perform the daily update process"""
    try:
        print(f"Starting daily update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        html_file = create_daily_html()
        push_to_github(html_file)
        print(f"Daily update completed successfully")
    except Exception as e:
        print(f"Error in daily update process: {e}")

def run_scheduled_updates():
    """Run the scheduled updates continuously"""
    # Schedule the task to run daily at 00:01
    schedule.every().day.at("00:01").do(daily_update)
    
    print("Scheduled daily updates. Keep this script running for automatic updates.")
    print(f"Next update scheduled for: {schedule.next_run()}")
    
    # Run once immediately
    daily_update()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def setup_instructions():
    """Print setup instructions"""
    print("""
    === GUESTHOUSE MANAGEMENT AUTOMATION SETUP ===
    
    STEP 1: GOOGLE SHEETS SETUP
    ---------------------------
    1. Go to Google Cloud Console (https://console.cloud.google.com/)
    2. Create a new project
    3. Enable the Google Sheets API and Google Drive API
    4. Create service account credentials and download the JSON key file
    5. Create a Google Sheet from your Excel booking tracker
    6. Share the sheet with the email address from the service account
    7. Share the sheet with the guesthouse owners (with edit permissions)
    
    STEP 2: GITHUB PAGES SETUP
    -------------------------
    1. Create a GitHub account if you don't have one
    2. Create a new repository (e.g., "guesthouse-schedule")
    3. Clone the repository to your laptop
    4. In repository settings, enable GitHub Pages on the main branch
    
    STEP 3: CONFIGURATION
    --------------------
    Update the following variables in this script:
    - GOOGLE_CREDENTIALS_FILE: path to your Google service account JSON file
    - SPREADSHEET_NAME: name of your Google Sheet
    - HTML_OUTPUT_DIR: directory where HTML files will be saved
    - GITHUB_REPO_PATH: path to your local GitHub repository
    
    STEP 4: AUTOSTART
    ---------------
    1. Windows: Use Task Scheduler to run this script at startup
       - Open Task Scheduler
       - Create a new task
       - Set it to run at startup
       - Action: Start a program
       - Program/script: python
       - Arguments: path/to/this/script.py
    
    2. Mac/Linux: Use crontab
       - Add this line to crontab:
         @reboot python /path/to/this/script.py
    
    USAGE INSTRUCTIONS FOR OWNERS
    ----------------------------
    1. Access today's schedule at: https://[your-username].github.io/[repo-name]/
    2. Add or modify bookings directly in the shared Google Sheet
    3. The schedule will update automatically every day
    """)

if __name__ == "__main__":
    # Show setup instructions
    setup_instructions()
    
    # Uncomment to start the scheduled updates
    # run_scheduled_updates()