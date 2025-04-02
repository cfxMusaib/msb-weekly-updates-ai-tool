# 📝 Weekly Work Updates Generator (by Musaib)

This Python script automates the generation of a **weekly engineering status report** from Bitbucket commit messages and appends it to a **Google Docs document**. It uses **Gemini AI** to intelligently summarize commit activity into three sections:
- ✅ Tasks completed 100%
- 🛠 Tasks continue to work on
- 🆕 New tasks started

---

## 📦 Features

- 🔐 Authenticates with Bitbucket using app passwords.
- 📊 Filters commits by allowed emails/usernames.
- 🧠 Summarizes commit messages using Google's **Gemini API**.
- 📝 Appends the summary in a structured format to a **Google Doc**.
---

## ⚙️ Requirements

- Python 3.7+
- Google Cloud project with Docs API enabled
- Google service account with access to your Google Doc
- Bitbucket app password for API access
- Gemini API Key

---

## 📁 Installation

```bash
# Clone the repo
git clone https://github.com/cfxMusaib/msb-weekly-updates-ai-tool.git
cd msb-weekly-updates-ai-tool

# Install dependencies
pip install -r requirements.txt
```

## Setup .env file
```
# Gemini API Key
GEMINI_API_KEY=your_gemini_api_key

# Bitbucket
BITBUCKET_USERNAME=your_bitbucket_username
BITBUCKET_APP_PASSWORD=your_bitbucket_app_password
WORKSPACE=your_bitbucket_workspace
REPO_SLUG=your_repository_slug

# Google Docs
GOOGLE_CREDENTIALS_SERVICE_ACCOUNT_FILE=path/to/your/credentials.json
GOOGLE_DOC_ID=your_google_doc_id
```

### Gemini API Key
- Go to https://aistudio.google.com/app/apikey
- Click Create API Key.
- Copy the key and paste it in .env under GEMINI_API_KEY.

### Bitbucket App Password
- Visit: https://bitbucket.org/account/settings/app-passwords/
- Click Create app password.
- Select the required repository and permission scopes:
    - Repositories: Read
    - Account: Read
- Save the generated password and add it to .env as BITBUCKET_APP_PASSWORD.

### Google Docs API & Credentials
- Go to Google Cloud Console.
- Create a new project (or use an existing one).
- Enable the Google Docs API and Google Drive API.
- Go to IAM & Admin > Service Accounts:
    - Create a service account.
    - Generate a JSON key and save it.
    - Share your target Google Doc with the service account email (like a normal user) with Editor access.
- Save the JSON key and update GOOGLE_CREDENTIALS_FILE path in .env.

```
Important 🚨: After created the service account. Add the service account email to google doc access share list as "Editor".
```

## Running the Script
```bash
python script.py
```

## 📅 Schedule It (Optional)
To run it weekly, you can set up a cron job:
```bash
0 9 * * MON /usr/bin/python3 /path/to/main.py >> /path/to/weekly_log.txt 2>&1
```