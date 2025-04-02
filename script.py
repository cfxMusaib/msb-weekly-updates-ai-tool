import requests
from datetime import datetime, timedelta, timezone, date
import re
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

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


def get_commits():
    url = f"https://api.bitbucket.org/2.0/repositories/{WORKSPACE}/{REPO_SLUG}/commits"
    auth = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)

    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
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
            if commit_date < one_week_ago:
                stop_fetching = True
                break

            author = commit.get("author", {})
            raw_email = author.get("raw", "")
            username = author.get("user", {}).get("username", "")

            if not any(email in raw_email for email in allowed_emails) and username not in allowed_usernames:
                continue

            message = commit["message"].strip()
            date_only = commit_date.strftime("%Y-%m-%d")
            commits.append(f"{date_only}: {message}")

        if stop_fetching or not data.get("next"):
            break

        url = data["next"]

    return commits

def get_structured_update_from_gemini(commits):
    raw_text = "\n".join(commits)
    prompt = f"""
You are preparing a weekly engineering status report using the commit messages below.

Organize the output into **three sections**:
1. Tasks completed 100%
2. Tasks continue to work on
3. New tasks started

Format the output like:
<completed>
-• task 1
</completed>

<inprogress>
-• task 1
</inprogress>

<new>
-• task 1
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
    date_heading = f"Weekly Update: {period_from} to {period_to}\n\n"
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

    # Insert each section with bullet points
    cursor = end_index + len(date_heading)
    for title, data in zip(section_titles, task_data):
        bullet_lines = [line.strip("-• ").strip() for line in data.splitlines() if line.strip()]
        bullet_text = "\n".join(bullet_lines) + "\n"

        # Insert section title
        requests.append({"insertText": {"location": {"index": cursor}, "text": title + "\n"}})
        cursor += len(title) + 1

        # Insert bullet items
        requests.append({"insertText": {"location": {"index": cursor}, "text": bullet_text}})
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


if __name__ == "__main__":
    commits = get_commits()
    if not commits:
        print("No commits in the past 7 days.")
        exit()

    gemini_response = get_structured_update_from_gemini(commits)
    parsed_info = parse_structured_response(gemini_response)
    # print("======PARSED======")
    # print(parsed_info)

    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/documents"]
    )
    service = build("docs", "v1", credentials=creds)

    doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
    end_index = doc['body']['content'][-1]['endIndex']

    today = date.today()
    period_start = (today - timedelta(days=7)).strftime("%d-%m-%Y")
    period_end = today.strftime("%d-%m-%Y")

    append_bullet_summary_to_doc(service, GOOGLE_DOC_ID, end_index, period_start, period_end, parsed_info)
    print("✅ Weekly status report added to Google Doc.")
