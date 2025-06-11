# 🚀 Weekly AI Status Report Bot

This repository contains an automated bot that generates a **weekly engineering status report** and posts it to a Google Doc.

It runs automatically every Monday using GitHub Actions, fetches the previous week's commit messages from a Bitbucket repository, uses **Google's Gemini AI** to write a summary, and appends it to your document. Set it up once, and never write a manual weekly update again.

## ✨ How It Works

1.  **Scheduled Trigger**: A GitHub Actions workflow, included in this repository, runs at 8:00 AM UTC every Monday.
2.  **Fetch Commits**: The Python script (`script.py`) fetches all relevant commits from the specified Bitbucket repository from the previous week.
3.  **AI Summarization**: The commit messages are sent to the **Gemini API**, which intelligently organizes them into three categories:
      - ✅ Tasks Completed
      - 🛠️ Tasks in Progress
      - 🆕 New Tasks Started
4.  **Update Google Doc**: The script formats this summary into a clean table and appends it to your designated Google Doc.

-----

## ⚙️ Setup Guide (2 Steps)

Follow these two steps to configure your automated report bot.

### Step 1: Gather Your Credentials

You'll need the following keys and IDs. It's recommended to gather them all before moving to the next step.

<details>
  <summary>
    <strong>Click here for instructions on getting your credentials. </strong>
  </summary>

1.  **Gemini API Key**

      - Go to [Google AI Studio's API Key page](https://aistudio.google.com/app/apikey).
      - Click `Create API Key` and copy the generated key.

2.  **Bitbucket App Password**

      - Navigate to your Bitbucket [App passwords settings](https://bitbucket.org/account/settings/app-passwords/).
      - Click `Create app password`, give it a descriptive name (e.g., `report-bot`).
      - Grant it these two permissions:
          - `repositories` \> `Read`
          - `account` \> `Read`
      - Copy the generated password immediately. **You will not see it again.**

3.  **Google Service Account & Doc ID**

      - **Enable APIs**: In the [Google Cloud Console](https://console.cloud.google.com/), select a project and ensure the **Google Docs API** and **Google Drive API** are enabled.
      - **Create Service Account**: Go to `IAM & Admin` \> `Service Accounts` and click `CREATE SERVICE ACCOUNT`.
      - **Generate JSON Key**: After creating the account, find it in the list, click the `Actions` menu (⋮), and select `Manage keys`. Click `ADD KEY` \> `Create new key`, choose **JSON**, and a `.json` file will be downloaded. Keep this file handy.
      - **Share Google Doc**: Open the Google Doc you want to update. Click the `Share` button and paste the service account's email address (e.g., `...gserviceaccount.com`). Grant it **Editor** access.
      - **Get Doc ID**: The Google Doc ID is the long string of characters in its URL: `https://docs.google.com/document/d/THIS_IS_THE_DOC_ID/edit`. Copy this ID.

</details>

### Step 2: Configure GitHub Secrets

In your GitHub repository, go to `Settings` \> `Secrets and variables` \> `Actions`. Add the following secrets, pasting the credentials you gathered in Step 1. This is the only configuration you need to do.

| Secret Name                             | Value                                                              |
| --------------------------------------- | ------------------------------------------------------------------ |
| `GEMINI_API_KEY`                        | Your key from Google AI Studio.                                    |
| `BITBUCKET_USERNAME`                    | Your Bitbucket username.                                           |
| `BITBUCKET_EMAIL`                       | Your Bitbucket account email.                                      |
| `BITBUCKET_APP_PASSWORD`                | Your Bitbucket app password.                                       |
| `WORKSPACE`                             | Your Bitbucket workspace ID.                                       |
| `REPO_SLUG`                             | Your Bitbucket repository slug.                                    |
| `GOOGLE_DOC_ID`                         | The ID of your target Google Doc.                                  |
| `GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE` | **Paste the entire content** of the `.json` file you downloaded. |

-----

## 🤖 Understanding the Automation

This repository includes a pre-configured GitHub Actions workflow file at `.github/workflows/main.yml`. This file defines all the automation. Here is its content:

```yaml
# .github/workflows/main.yml

name: Generate Weekly Status Report

on:
  # Allows you to run this workflow manually from the Actions tab
  workflow_dispatch:

  # Runs automatically at 8:00 AM IST (2:30 AM UTC) every Monday
  schedule:
    - cron: '30 2 * * 1'

jobs:
  generate-report:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Create Google Credentials File from Secret
        env:
          CREDENTIALS_JSON: ${{ secrets.GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE }}
        run: echo "$CREDENTIALS_JSON" > service-account.json

      - name: Run Report Generation Script
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          BITBUCKET_USERNAME: ${{ secrets.BITBUCKET_USERNAME }}
          BITBUCKET_EMAIL: ${{ secrets.BITBUCKET_EMAIL }}
          BITBUCKET_APP_PASSWORD: ${{ secrets.BITBUCKET_APP_PASSWORD }}
          WORKSPACE: ${{ secrets.WORKSPACE }}
          REPO_SLUG: ${{ secrets.REPO_SLUG }}
          GOOGLE_DOC_ID: ${{ secrets.GOOGLE_DOC_ID }}
          GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE: service-account.json
        run: |
          # Runs the script for the previous week in table format
          python3 script.py --range last-week --format table
```

### Customization

  - **Format**: To change the report format from a table to bullet points, edit the last line of `main.yml` to be `--format bullet`.
  - **Schedule**: To change the schedule, edit the `cron:` value. You can use a tool like [crontab.guru](https://crontab.guru/) to help.

-----

## ✅ All Done\!

Once you have set up your secrets, the bot is active.

  - It will **run automatically** every Monday.
  - You can **trigger it manually** by going to your repository's `Actions` tab, selecting "Generate Weekly Status Report," and clicking `Run workflow`.

-----

## ✍️ Author

  - **Musaib (cfxMusaib)**