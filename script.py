import argparse
import os
import re
from datetime import datetime, timedelta, timezone, date

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Load environment variables from a .env file
load_dotenv()

# --- Environment Variables ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BITBUCKET_USERNAME = os.getenv("BITBUCKET_USERNAME")
BITBUCKET_EMAIL = os.getenv("BITBUCKET_EMAIL")
BITBUCKET_APP_PASSWORD = os.getenv("BITBUCKET_APP_PASSWORD")
WORKSPACE = os.getenv("WORKSPACE")
REPO_SLUG = os.getenv("REPO_SLUG")
GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE"
)
GOOGLE_DOC_ID = os.getenv("GOOGLE_DOC_ID")

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")


def get_commits(from_date=None, to_date=None):
    """
    Fetches commits from a Bitbucket repository within a specified date range.

    Args:
        from_date (datetime, optional): The start date for fetching commits.
        to_date (datetime, optional): The end date for fetching commits.

    Returns:
        tuple: A tuple containing the list of commits, the start date, and the end date.
    """
    url = f"https://api.bitbucket.org/2.0/repositories/{WORKSPACE}/{REPO_SLUG}/commits"
    auth = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)

    if not from_date or not to_date:
        return [], None, None

    commits = []
    allowed_emails = [BITBUCKET_EMAIL]
    allowed_usernames = [BITBUCKET_USERNAME]

    while url:
        response = requests.get(url, auth=auth)
        if response.status_code != 200:
            print(f"Bitbucket error: {response.status_code} {response.text}")
            break

        data = response.json()
        stop_fetching = False

        for commit in data.get("values", []):
            commit_date = datetime.strptime(
                commit["date"], "%Y-%m-%dT%H:%M:%S%z"
            )

            if commit_date < from_date:
                stop_fetching = True
                break

            if commit_date > to_date:
                continue  # Skip future commits

            author = commit.get("author", {})
            raw_email = author.get("raw", "")
            username = author.get("user", {}).get("username", "")

            if not any(
                email in raw_email for email in allowed_emails
            ) and username not in allowed_usernames:
                continue

            message = commit["message"].strip()

            # Skip merge commits
            if re.match(r"(?i)^merge\b", message):
                continue

            hash_id = commit["hash"]
            commit_url = (
                f"https://bitbucket.org/{WORKSPACE}/{REPO_SLUG}/commits/{hash_id}"
            )
            date_only = commit_date.strftime("%Y-%m-%d")

            # Append structured data
            commits.append(
                {"date": date_only, "message": message, "url": commit_url}
            )

        if stop_fetching or not data.get("next"):
            break

        url = data.get("next")

    return commits, from_date, to_date


def get_structured_update_from_gemini(commits):
    """
    Generates a structured summary of commits using the Gemini API.

    Args:
        commits (list): A list of commit dictionaries.

    Returns:
        str: The structured summary from Gemini.
    """
    raw_text = "\n".join(
        f"{c['date']}: {c['message']} ({c['url']})" for c in commits
    )
    prompt = f"""
        You are preparing a weekly engineering status report using the commit messages below.

        Organize the output into **three sections**:
        1. Tasks completed 100%
        2. Tasks continue to work on
        3. New tasks started

        Note: Feel free to elaborate the commit messages if needed but don't club the tasks together.

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
    return response.text.strip()


def parse_structured_response(response):
    """
    Parses the structured response from Gemini.

    Args:
        response (str): The response text from Gemini.

    Returns:
        dict: A dictionary with 'completed', 'inprogress', and 'new' tasks.
    """

    def extract(tag):
        pattern = fr"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, response, re.DOTALL)
        return match.group(1).strip() if match else ""

    return {
        "completed": extract("completed"),
        "inprogress": extract("inprogress"),
        "new": extract("new"),
    }


def append_bullet_summary_to_doc(
    service, doc_id, end_index, period_from, period_to, parsed_info
):
    """
    Appends a bullet-point summary to a Google Doc.

    Args:
        service: The Google Docs API service object.
        doc_id (str): The ID of the Google Doc.
        end_index (int): The index at which to start inserting content.
        period_from (str): The start date of the report period.
        period_to (str): The end date of the report period.
        parsed_info (dict): The dictionary of parsed tasks.
    """
    date_heading = f"Weekly Status Report\n"
    section_titles = [
        "1. Tasks completed 100%:",
        "2. Tasks continue to work on:",
        "3. New tasks started:",
    ]
    task_data = [
        parsed_info["completed"],
        parsed_info["inprogress"],
        parsed_info["new"],
    ]

    requests = []

    # Add a page break and heading
    requests.append({"insertPageBreak": {"location": {"index": end_index - 1}}})
    requests.append(
        {"insertText": {"location": {"index": end_index}, "text": date_heading}}
    )

    # Style the heading
    heading_start = end_index
    heading_end = heading_start + len(date_heading)
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": heading_start, "endIndex": heading_end},
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 20, "unit": "PT"},
                    "weightedFontFamily": {"fontFamily": "Arial"},
                },
                "fields": "bold,fontSize,weightedFontFamily",
            }
        }
    )

    # Insert each section with bullet points
    cursor = end_index + len(date_heading)
    for title, data in zip(section_titles, task_data):
        bullet_lines = [
            line.strip("-• ").strip()
            for line in data.splitlines()
            if line.strip()
        ]
        bullet_text = "\n".join(bullet_lines) + "\n"

        # Insert section title
        title_text = title + "\n"
        requests.append(
            {"insertText": {"location": {"index": cursor}, "text": title_text}}
        )
        cursor += len(title_text)

        # Insert bullet items
        bullet_text_start = cursor
        requests.append(
            {
                "insertText": {
                    "location": {"index": bullet_text_start},
                    "text": bullet_text,
                }
            }
        )
        requests.append(
            {
                "createParagraphBullets": {
                    "range": {
                        "startIndex": cursor,
                        "endIndex": cursor + len(bullet_text),
                    },
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            }
        )
        cursor += len(bullet_text)

    service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()


def append_table_summary_to_doc(
    service, doc_id, end_index, period_from, period_to, parsed_info
):
    """
    Appends a table summary to a Google Doc.

    Args:
        service: The Google Docs API service object.
        doc_id (str): The ID of the Google Doc.
        end_index (int): The index at which to start inserting content.
        period_from (str): The start date of the report period.
        period_to (str): The end date of the report period.
        parsed_info (dict): The dictionary of parsed tasks.
    """

    def format_bullet_text(text, tag):
        lines = [
            line.strip("-• ").strip()
            for line in text.splitlines()
            if line.strip()
        ]
        bullet = ""
        if tag == "completed":
            bullet = "✅"
        elif tag == "inprogress":
            bullet = "⏳"
        elif tag == "new":
            bullet = "🆕"
        return "\n".join(f"{bullet} {line}" for line in lines) if lines else ""

    table_rows = [
        f"Period from {period_from} to {period_to}",
        "1. Tasks completed 100%:\n"
        + format_bullet_text(parsed_info["completed"], "completed"),
        "2. Tasks continue to work on:\n"
        + format_bullet_text(parsed_info["inprogress"], "inprogress"),
        "3. New tasks started:\n"
        + format_bullet_text(parsed_info["new"], "new"),
    ]

    requests = [{"insertPageBreak": {"location": {"index": end_index - 1}}}]
    date_heading = f"Weekly Status Report\n"
    requests.append(
        {"insertText": {"location": {"index": end_index}, "text": date_heading}}
    )

    heading_start = end_index
    heading_end = heading_start + len(date_heading)
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": heading_start, "endIndex": heading_end},
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 20, "unit": "PT"},
                    "weightedFontFamily": {"fontFamily": "Arial"},
                },
                "fields": "bold,fontSize,weightedFontFamily",
            }
        }
    )
    requests.append(
        {
            "insertTable": {
                "rows": len(table_rows),
                "columns": 1,
                "location": {"index": heading_end},
            }
        }
    )

    service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    doc = service.documents().get(documentId=doc_id).execute()
    content = doc["body"]["content"]
    tables = [elem for elem in content if "table" in elem]
    if not tables:
        raise ValueError("❌ Table not found in document.")
    table = tables[-1]

    cell_indexes = [
        row["tableCells"][0]["content"][0]["paragraph"]["elements"][0][
            "startIndex"
        ]
        for row in table["table"]["tableRows"]
    ]

    text_requests = []
    for text, index in reversed(list(zip(table_rows, cell_indexes))):
        text_requests.append(
            {"insertText": {"location": {"index": index}, "text": text}}
        )

    service.documents().batchUpdate(
        documentId=doc_id, body={"requests": text_requests}
    ).execute()


def main():
    """
    Main function to run the report generation script.
    """
    parser = argparse.ArgumentParser(
        description="Generate a weekly status report from Bitbucket commits."
    )
    parser.add_argument(
        "--range",
        choices=["this-week", "last-week"],
        help="Pre-defined date range. Overrides --from-date and --to-date.",
    )
    parser.add_argument(
        "--from-date",
        help="Start date in YYYY-MM-DD format. Required if --range is not used.",
    )
    parser.add_argument(
        "--to-date",
        help="End date in YYYY-MM-DD format. Required if --range is not used.",
    )
    parser.add_argument(
        "--format",
        required=True,
        choices=["table", "bullet"],
        help="Report format: 'table' or 'bullet'.",
    )
    args = parser.parse_args()

    from_date = None
    to_date = None

    if args.range:
        today = datetime.now(timezone.utc)
        if args.range == "this-week":
            # Sunday is 6, Monday is 0. We consider Sunday the start of the week.
            days_since_sunday = (today.weekday() + 1) % 7
            from_date = (today - timedelta(days=days_since_sunday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            to_date = from_date + timedelta(
                days=6, hours=23, minutes=59, seconds=59
            )
        elif args.range == "last-week":
            days_since_sunday = (today.weekday() + 1) % 7
            last_sunday = (
                today - timedelta(days=days_since_sunday + 7)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            from_date = last_sunday
            to_date = from_date + timedelta(
                days=6, hours=23, minutes=59, seconds=59
            )
    elif args.from_date and args.to_date:
        try:
            from_date = datetime.strptime(args.from_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            to_date = datetime.strptime(args.to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            if to_date < from_date:
                raise ValueError("End date cannot be before start date.")
        except ValueError as e:
            print(f"Error processing dates: {e}")
            exit(1)
    else:
        parser.error(
            "Please specify a date range using --range or both --from-date and --to-date."
        )

    print("Fetching commits...")
    commits, _, _ = get_commits(from_date=from_date, to_date=to_date)

    if not commits:
        print("No commits found in the selected date range.")
        exit()
    print(f"Found {len(commits)} commits.")

    print("Generating summary with Gemini...")
    gemini_response = get_structured_update_from_gemini(commits)
    parsed_info = parse_structured_response(gemini_response)
    print("Summary generated.")

    print("Writing to Google Doc...")
    try:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/documents"],
        )
        service = build("docs", "v1", credentials=creds)

        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        end_index = doc["body"]["content"][-1]["endIndex"]

        period_start = from_date.strftime("%d-%m-%Y")
        period_end = to_date.strftime("%d-%m-%Y")

        if args.format == "table":
            append_table_summary_to_doc(
                service,
                GOOGLE_DOC_ID,
                end_index,
                period_start,
                period_end,
                parsed_info,
            )
        else:
            append_bullet_summary_to_doc(
                service,
                GOOGLE_DOC_ID,
                end_index,
                period_start,
                period_end,
                parsed_info,
            )

        print("✅ Weekly status report added to Google Doc.")
    except Exception as e:
        print(f"An error occurred while writing to Google Docs: {e}")
        exit(1)


if __name__ == "__main__":
    main()