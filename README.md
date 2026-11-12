# Smart Lost Item Finder for College

A Flask + SQLite educational web application for reporting lost/found items and suggesting possible matches using text similarity, category, and location.

## Features
- Student registration and sign-in/sign-out
- Password hashing (passwords are not stored as plain text)
- Report lost or found items after signing in
- Search and filter reports by text, type, category, and status
- Smart suggestions based on description/title similarity, category, and location
- My Reports page
- Report owners can update status or delete their own reports
- SQLite persistence in `lost_found.db`
- Responsive Bootstrap layout
- Database migration adds `user_id` when opening an older database

## Requirements
- Python 3.10 or later recommended
- Internet connection on first browser load for Bootstrap CDN styling (the app still functions without styling)

## Run on Windows (VS Code)
1. Extract this ZIP completely.
2. In VS Code, open the extracted `smart_lost_item_finder_complete` folder (the folder containing `app.py` and `requirements.txt`).
3. Open **Terminal → New Terminal**. Make sure the prompt is in the project folder, not inside `venv`.
4. Create a virtual environment if needed:
   ```cmd
   py -m venv venv
   ```
5. Activate it. In PowerShell:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, switch terminal profile to **Command Prompt** and run:
   ```cmd
   venv\Scripts\activate.bat
   ```
6. Install dependencies:
   ```cmd
   python -m pip install -r requirements.txt
   ```
7. Start the app:
   ```cmd
   python app.py
   ```
8. Open http://127.0.0.1:5000 in your browser.

## First test
1. Click Register and create a demo account.
2. Sign in.
3. Report a lost item such as `Black wireless earbuds`.
4. Report a found item such as `Black Bluetooth earphones`.
5. Open one report and inspect Possible Matches.
6. Visit My Reports to update status or delete your own report.
7. Inspect `lost_found.db` with DB Browser for SQLite if you want to see stored records.

## Database
The app automatically creates `users` and `items` tables on startup. The database file is stored beside `app.py`. Existing database files are retained; startup attempts to add the `user_id` column if an older `items` table does not have it.

## Important limitations and safety
- Matching is a heuristic suggestion, not AI/ML and not proof of ownership.
- This is a local educational demo, not production-ready. It uses Flask's development server and a fallback development secret key. Before deployment, set a strong random `SECRET_KEY`, turn off debug mode (`FLASK_DEBUG=0`), use HTTPS and a production WSGI server, add CSRF protection/rate limiting, and review privacy/access controls.
- Contact name/email from the signed-in account are shown on reports. Use demo contact details for a classroom presentation and avoid publishing sensitive information.
- This project does not verify whether a person is the true owner of an item.
