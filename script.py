import requests
from datetime import datetime, timedelta, timezone, date
import re
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
import inquirer
from yaspin import yaspin

import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BITBUCKET_USERNAME = os.getenv("BITBUCKET_USERNAME")
BITBUCKET_APP_PASSWORD = os.getenv("BITBUCKET_APP_PASSWORD")
WORKSPACE = os.getenv("WORKSPACE")
REPO_SLUG = os.getenv("REPO_SLUG")
GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE")
GOOGLE_DOC_ID = os.getenv("GOOGLE_DOC_ID")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")


def get_commits(from_date=None, to_date=None):
    url = f"https://api.bitbucket.org/2.0/repositories/{WORKSPACE}/{REPO_SLUG}/commits"
    auth = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)

    if not from_date or not to_date:
        return [], None, None

    commits = []
    allowed_emails = ["musaib.ali@cloudfabrix.com"]
    allowed_usernames = ["mdmusaibali"]

    while url:
        response = requests.get(url, auth=auth)
        if response.status_code != 200:
            print("Bitbucket error:", response.status_code, response.text)
            break

        data = response.json()
        stop_fetching = False

        for commit in data.get("values", []):
            commit_date = datetime.strptime(commit["date"], "%Y-%m-%dT%H:%M:%S%z")

            if commit_date < from_date:
                stop_fetching = True
                break

            if commit_date > to_date:
                continue  # skip future commits

            author = commit.get("author", {})
            raw_email = author.get("raw", "")
            username = author.get("user", {}).get("username", "")

            if not any(email in raw_email for email in allowed_emails) and username not in allowed_usernames:
                continue

            message = commit["message"].strip()
            hash_id = commit["hash"]
            commit_url = f"https://bitbucket.org/{WORKSPACE}/{REPO_SLUG}/commits/{hash_id}"
            date_only = commit_date.strftime("%Y-%m-%d")
            # Append structured data
            commits.append({
                "date": date_only,
                "message": message,
                "url": commit_url
            })

        if stop_fetching or not data.get("next"):
            break

        url = data.get("next")

    return commits, from_date, to_date

def get_structured_update_from_gemini(commits):
    raw_text = "\n".join(f"{c['date']}: {c['message']} ({c['url']})" for c in commits)
    prompt = f"""
        You are preparing a weekly engineering status report using the commit messages below.

        Organize the output into **three sections**:
        1. Tasks completed 100%
        2. Tasks continue to work on
        3. New tasks started

        Format the output like:
        <completed>
        -• task 1 (url)
        </completed>

        <inprogress>
        -• task 1 (url)
        </inprogress>

        <new>
        -• task 1 (url)
        </new>

        Commit messages:
        {raw_text}
    """
    response = gemini_model.generate_content(prompt)
    # print("=======GEMINI RESPONSE=========")
    # print(response)
    return response.text.strip()

def parse_structured_response(response):
    def extract(tag):
        pattern = fr"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, response, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    return {
        "completed": extract("completed"),
        "inprogress": extract("inprogress"),
        "new": extract("new")
    }

def append_bullet_summary_to_doc(service, doc_id, end_index, period_from, period_to, parsed_info):
    date_heading = f"Weekly Status Report\n"
    section_titles = [
        "1. Tasks completed 100%:",
        "2. Tasks continue to work on:",
        "3. New tasks started:"
    ]
    task_data = [parsed_info['completed'], parsed_info['inprogress'], parsed_info['new']]

    requests = []

    # Add a page break and heading
    requests.append({"insertPageBreak": {"location": {"index": end_index - 1}}})
    requests.append({"insertText": {"location": {"index": end_index}, "text": date_heading}})

    # After inserting the heading text:
    heading_start = end_index
    heading_end = heading_start + len(date_heading)

    # Add a request to update the heading style: font size 20, Arial, and bold.
    requests.append({
        "updateTextStyle": {
            "range": {
                "startIndex": heading_start,
                "endIndex": heading_end
            },
            "textStyle": {
                "bold": True,
                "fontSize": {
                    "magnitude": 20,
                    "unit": "PT"
                },
                "weightedFontFamily": {
                    "fontFamily": "Arial"
                }
            },
            "fields": "bold,fontSize,weightedFontFamily"
        }
    })

    # Insert each section with bullet points
    cursor = end_index + len(date_heading)
    for title, data in zip(section_titles, task_data):
        bullet_lines = [line.strip("-• ").strip() for line in data.splitlines() if line.strip()]
        bullet_text = "\n".join(bullet_lines) + "\n"

        # Insert section title
        title_text = title + "\n"
        requests.append({"insertText": {"location": {"index": cursor}, "text": title_text}})
        cursor += len(title_text)

        # Store the start index for bullet text insertion
        bullet_text_start = cursor

        # Insert bullet items
        requests.append({"insertText": {"location": {"index": bullet_text_start}, "text": bullet_text}})
        requests.append({
            "createParagraphBullets": {
                "range": {
                    "startIndex": cursor,
                    "endIndex": cursor + len(bullet_text)
                },
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
            }
        })
        cursor += len(bullet_text)

    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

def append_table_summary_to_doc(service, doc_id, end_index, period_from, period_to, parsed_info):
    def format_bullet_text(text, tag):
        lines = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]
        bullet = ""
        if tag == 'completed':
            bullet = "✅"
        elif tag == 'inprogress':
            bullet = "⏳"
        elif tag == 'new':
            bullet = "🆕"
        return "\n".join(f"{bullet} {line}" for line in lines) if lines else ""
    
    # Prepare text for the 4 table rows
    table_rows = [
        f"Period from {period_from} to {period_to}",
        "1. Tasks completed 100%:\n" + format_bullet_text(parsed_info['completed'], 'completed'),
        "2. Tasks continue to work on:\n" + format_bullet_text(parsed_info['inprogress'], 'inprogress'),
        "3. New tasks started:\n" + format_bullet_text(parsed_info['new'], 'new')
    ]

    # Step 1: Insert page break and table
    requests = [
        {"insertPageBreak": {"location": {"index": end_index - 1}}}
    ]

    # Add a heading for the table
    date_heading = f"Weekly Status Report\n"
    requests.append({"insertText": {"location": {"index": end_index}, "text": date_heading}})

    # After inserting the heading text:
    heading_start = end_index
    heading_end = heading_start + len(date_heading)

    # Add a request to update the heading style: font size 20, Arial, and bold.
    requests.append({
        "updateTextStyle": {
            "range": {
                "startIndex": heading_start,
                "endIndex": heading_end
            },
            "textStyle": {
                "bold": True,
                "fontSize": {
                    "magnitude": 20,
                    "unit": "PT"
                },
                "weightedFontFamily": {
                    "fontFamily": "Arial"
                }
            },
            "fields": "bold,fontSize,weightedFontFamily"
        }
    })

    # insert the table
    requests.append({
        "insertTable": {
            "rows": len(table_rows),
            "columns": 1,
            "location": {
                "index": heading_end
            }
        }
    })

    # Send request to insert the table
    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    # Step 2: Fetch document to get cell start indices
    doc = service.documents().get(documentId=doc_id).execute()
    content = doc['body']['content']
    tables = [elem for elem in content if 'table' in elem]
    if not tables:
        raise ValueError("❌ Table not found in document.")
    table = tables[-1]  # ✅ Get the most recent (last) table

    # Step 3: Get startIndex for each cell
    cell_indexes = []
    for row in table['table']['tableRows']:
        cell = row['tableCells'][0]
        cell_indexes.append(cell['content'][0]['paragraph']['elements'][0]['startIndex'])
    
    # print("Cell indexes:", cell_indexes)

    # # Step 4: Insert the actual text into each cell
    text_requests = []
    for text, index in reversed(list(zip(table_rows, cell_indexes))):
        text_requests.append({
            "insertText": {
                "location": {"index": index},
                "text": text
            }
        })

    # # Send request to insert text
    service.documents().batchUpdate(documentId=doc_id, body={"requests": text_requests}).execute()



def prompt_date_range():
    questions = [
        inquirer.List(
            "range_type",
            message="Which date range do you want to generate the report for?",
            choices=["This week", "Last week", "Custom"],
        )
    ]
    answers = inquirer.prompt(questions)

    today = datetime.now(timezone.utc)

    if answers["range_type"] == "This week":
        days_since_sunday = (today.weekday() + 1) % 7
        from_date = (today - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
        to_date = from_date + timedelta(days=6, hours=23, minutes=59, seconds=59)

    elif answers["range_type"] == "Last week":
        days_since_sunday = (today.weekday() + 1) % 7
        last_sunday = (today - timedelta(days=days_since_sunday + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = last_sunday
        to_date = from_date + timedelta(days=6, hours=23, minutes=59, seconds=59)

    else:  # Custom
        date_inputs = inquirer.prompt([
            inquirer.Text("from_date", message="Enter start date (YYYY-MM-DD)"),
            inquirer.Text("to_date", message="Enter end date (YYYY-MM-DD)")
        ])
        from_date = datetime.strptime(date_inputs["from_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        to_date = datetime.strptime(date_inputs["to_date"], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

        if to_date < from_date:
            raise ValueError("❌ End date cannot be before start date.")

    return from_date, to_date

def prompt_format_choice():
    choice = inquirer.prompt([
        inquirer.List(
            "format",
            message="Choose how to display the report:",
            choices=["Table format", "Bullet format"],
        )
    ])
    return choice["format"]


if __name__ == "__main__":
    from_date, to_date = prompt_date_range()
    report_format = prompt_format_choice()

    with yaspin(text="Fetching commits...", color="cyan") as spinner:
        commits, _, _ = get_commits(from_date=from_date, to_date=to_date)

        if not commits:
            spinner.fail("💥")
            print("No commits in selected range.")
            exit()
        spinner.ok("✅")

    with yaspin(text="Asking Gemini for summary...", color="yellow") as spinner:
        gemini_response = get_structured_update_from_gemini(commits)
        parsed_info = parse_structured_response(gemini_response)
        spinner.ok("🤖")

    with yaspin(text="Writing to Google Doc...", color="green") as spinner:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/documents"]
        )
        service = build("docs", "v1", credentials=creds)

        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        end_index = doc['body']['content'][-1]['endIndex']

        period_start = from_date.strftime("%d-%m-%Y")
        period_end = to_date.strftime("%d-%m-%Y")

        if report_format == "Table format":
            append_table_summary_to_doc(service, GOOGLE_DOC_ID, end_index, period_start, period_end, parsed_info)
        else:
            append_bullet_summary_to_doc(service, GOOGLE_DOC_ID, end_index, period_start, period_end, parsed_info)

        spinner.ok("📄")

    print("✅ Weekly status report added to Google Doc.")
