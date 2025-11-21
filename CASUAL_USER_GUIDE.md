# Investment Memo Orchestrator
## Casual User Guide for Non-Technical Users

Welcome! This guide will walk you through installing and using the Investment Memo Orchestrator, even if you've never used a command line before. Don't worry—we'll explain everything step by step.

---

## Table of Contents

1. [What You'll Need](#what-youll-need)
2. [Understanding the Basics](#understanding-the-basics)
   - What is a Terminal?
   - What is Homebrew? (macOS - IMPORTANT!)
   - What is Git, Python, and uv?
3. [Step 1: Open Your Terminal](#step-1-open-your-terminal)
4. [Step 2: Check What You Already Have](#step-2-check-what-you-already-have)
5. [Step 3: Install Missing Tools](#step-3-install-missing-tools)
   - **(macOS)** Install Homebrew FIRST!
   - Install Git, Python 3.11, and uv
6. [Step 4: Get the Code](#step-4-get-the-code)
7. [Step 5: Set Up Your Workspace](#step-5-set-up-your-workspace)
8. [Step 6: Configure Your API Keys](#step-6-configure-your-api-keys)
9. [Step 7: Generate Your First Memo](#step-7-generate-your-first-memo)
10. [Step 8: Export Your Memo](#step-8-export-your-memo)
11. [Common Problems and Solutions](#common-problems-and-solutions)
12. [Updating the Application](#updating-the-application)
13. [Getting Help](#getting-help)

---

## What You'll Need

Before we start, here's what you'll need to gather:

- **A computer** running macOS, Windows, or Linux
- **Internet connection** (for downloading tools and searching the web)
- **API Keys** (we'll explain where to get these):
  - Anthropic API key (required - for Claude AI)
  - Tavily API key (optional but recommended - for web research)
  - Perplexity API key (optional - for citations)
- **About 30 minutes** for the initial setup

---

## Understanding the Basics

### What is a "Terminal"?

A **terminal** (also called "command line" or "command prompt") is a text-based interface where you type commands to tell your computer what to do. Think of it like a conversation with your computer using text instead of clicking buttons.

Don't worry—we'll give you the exact commands to type!

### AI Terminal Emulators

If you are willing to spend money on a subcription, [Warp Terminal](https://www.warp.dev/) is a great option. It has a lot of features that make it easier to use, and the conversational AI is capable of running accurate and complex commands.

### What is "Git"?

**Git** is a tool that helps manage code and track changes. Think of it like "track changes" in Microsoft Word, but for code. We use it to download the application code from the internet.

### What is "Python"?

**Python** is a programming language. This application is written in Python, so we need Python installed on your computer to run it.

### What is "uv"?

**uv** is a tool that helps install and manage Python packages (chunks of code that the application needs to work). It's faster and more reliable than the older tool called "pip".

### What is "Homebrew"? (macOS Users - READ THIS!)

**If you're on a Mac, Homebrew will make your life SO much easier!**

**Homebrew** is like the "App Store for developers" on macOS. Instead of downloading installers from websites, clicking through installation wizards, and manually updating software, Homebrew lets you install and update everything with simple commands.

**Why you should use Homebrew:**
- ✅ **One-command installs**: Instead of visiting websites, downloading, and clicking through installers
- ✅ **Automatic updates**: Update all your tools with one command: `brew upgrade`
- ✅ **Cleaner system**: Everything installs to one organized location
- ✅ **Uninstall easily**: Remove tools cleanly with `brew uninstall`
- ✅ **Thousands of tools**: Python, Git, Node.js, databases—all available instantly
- ✅ **Used by millions**: The standard way Mac developers install tools

**Think of it this way:** Without Homebrew, installing Python means:
1. Open browser
2. Go to python.org
3. Find the download page
4. Download the right installer
5. Open the downloaded file
6. Click through 6 installation steps
7. Hope it worked

**With Homebrew:**
```bash
brew install python@3.11
```
Done! ✨

**How to install Homebrew** (takes 2 minutes):

We'll do this in Step 3, but here's a preview:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Bottom line for Mac users:** Install Homebrew first, then use it to install everything else. You'll thank yourself later!

---

## Step 1: Open Your Terminal

### On macOS:

1. Press `Cmd + Space` to open Spotlight Search
2. Type "Terminal" and press Enter
3. A window with white or black background will appear—this is your terminal!

### On Windows:

1. Press `Windows + R` to open Run dialog
2. Type "cmd" and press Enter
3. A black window will appear—this is your command prompt!

Alternatively:
1. Click the Start menu
2. Type "Command Prompt" or "PowerShell"
3. Click on it to open

### On Linux:

1. Press `Ctrl + Alt + T` (on most systems)
2. Or find "Terminal" in your applications menu

---

## Step 2: Check What You Already Have

Let's check which tools are already installed on your computer. Copy and paste each command below into your terminal and press Enter.

### (macOS only) Check if Homebrew is installed:

```bash
brew --version
```

**What to expect:**
- ✅ **Good**: You see something like `Homebrew 4.x.x` → Homebrew is installed!
- ❌ **Not installed**: You see `command not found` → **INSTALL THIS FIRST!** (We'll do it in Step 3)

**Note:** If you don't have Homebrew, we **strongly recommend** installing it before anything else. It will make the rest of the setup much easier!

### Check if Git is installed:

```bash
git --version
```

**What to expect:**
- ✅ **Good**: You see something like `git version 2.39.0` → Git is installed!
- ❌ **Not installed**: You see an error like `command not found` → We'll install it in Step 3

### Check if Python 3.11+ is installed:

```bash
python3 --version
```

**What to expect:**
- ✅ **Good**: You see `Python 3.11.x` or `Python 3.12.x` → Python is ready!
- ❌ **Wrong version**: You see `Python 3.9.x` or `Python 3.10.x` → We need to install Python 3.11
- ❌ **Not installed**: You see an error → We'll install Python 3.11 in Step 3

### Check if uv is installed:

```bash
uv --version
```

**What to expect:**
- ✅ **Good**: You see a version number → uv is installed!
- ❌ **Not installed**: You see an error → We'll install it in Step 3

---

## Step 3: Install Missing Tools

Only follow the sections below for tools you don't have installed yet.

### (macOS ONLY) Install Homebrew FIRST!

**⭐ Mac users: Do this before installing anything else! ⭐**

If you don't have Homebrew installed (and you checked in Step 2), install it now:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**What to expect:**
- You'll see a welcome message explaining what Homebrew will do
- Press `Enter` to continue
- You may need to enter your Mac password (the cursor won't move—that's normal!)
- Installation takes 5-10 minutes
- At the end, you might see instructions about "adding Homebrew to your PATH"—**follow those instructions!**

**Common post-install step:**

You may need to run these commands (the installer will tell you):
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

**Or on older Intel Macs:**
```bash
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/usr/local/bin/brew shellenv)"
```

**Verify it worked:**
```bash
brew --version
```
You should see `Homebrew 4.x.x` or similar!

**🎉 Congratulations! You now have the Mac developer's best friend installed!**

Now you can install everything else with simple `brew install` commands.

---

### Install Git

#### On macOS:

**✨ RECOMMENDED: Install with Homebrew**

If you just installed Homebrew above, this is easy:
```bash
brew install git
```

That's it! No clicking through installers, no configuration needed.

**Alternative: Install Xcode Command Line Tools**

If you prefer not to use Homebrew (but why?):
```bash
xcode-select --install
```
- A popup window will appear asking you to install developer tools
- Click "Install" and wait for it to finish (5-15 minutes)
- This gives you Git plus other development tools

#### On Windows:

1. Go to [git-scm.com](https://git-scm.com/download/win)
2. Click "Download for Windows"
3. Run the installer
4. Use all default settings (just keep clicking "Next")
5. Close and reopen your terminal when done

#### On Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install git
```

**Verify it worked:**
```bash
git --version
```
You should see a version number!

---

### Install Python 3.11

#### On macOS:

**✨ RECOMMENDED: Install with Homebrew**

If you installed Homebrew in the step above (you did, right?), this is super easy:

```bash
brew install python@3.11
```

**What to expect:**
- Homebrew downloads and installs Python 3.11
- Takes about 2-3 minutes
- Automatically sets up everything correctly
- You're done! ✅

**Why Homebrew is better for Python:**
- ✅ Doesn't conflict with macOS system Python
- ✅ Easy to update: `brew upgrade python@3.11`
- ✅ Easy to uninstall: `brew uninstall python@3.11`
- ✅ Installs pip and other tools automatically
- ✅ Works perfectly with virtual environments

**Alternative: Download from Python.org (not recommended)**

Only do this if you really don't want to use Homebrew:

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the macOS installer for Python 3.11.x
3. Run the installer (use default settings)
4. Click through all the installation steps

But seriously, just use Homebrew. It's so much cleaner.

#### On Windows:

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download "Python 3.11.x" for Windows
3. Run the installer
4. **IMPORTANT**: Check the box "Add Python 3.11 to PATH" before clicking Install
5. Click "Install Now"
6. Close and reopen your terminal when done

#### On Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3.11-dev
```

**Verify it worked:**
```bash
python3.11 --version
```
You should see `Python 3.11.x`!

---

### Install uv

#### On macOS:

**✨ RECOMMENDED: Install with Homebrew**

Seeing a pattern here?
```bash
brew install uv
```

Done! No scripts to download, no PATH configuration needed.

**Alternative: Install with official script**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation completes, close and reopen your terminal.

#### On Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation completes, close and reopen your terminal.

#### On Windows:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation completes, close and reopen your terminal.

**Verify it worked:**
```bash
uv --version
```
You should see a version number!

---

## Step 4: Get the Code

Now we'll download the application code to your computer.

### Choose where to store the code

First, navigate to where you want to keep the code. We recommend your Documents folder:

**On macOS/Linux:**
```bash
cd ~/Documents
```

**On Windows:**
```bash
cd %USERPROFILE%\Documents
```

### Download the code

If this is a **private repository** (not public), you'll need access permissions first. Contact your team administrator.

**If you have repository access:**
```bash
git clone [REPOSITORY_URL_HERE]
```

Replace `[REPOSITORY_URL_HERE]` with the actual URL (should look like `https://github.com/your-org/investment-memo-orchestrator.git`).

**Example:**
```bash
git clone https://github.com/hypernova-capital/investment-memo-orchestrator.git
```

### Navigate into the folder

```bash
cd investment-memo-orchestrator
```

**What just happened?**
- `git clone` downloaded all the code files to your computer
- `cd` stands for "change directory"—it moves you into the folder we just downloaded

---

## Step 5: Set Up Your Workspace

Now we'll create a special environment for the application and install all the pieces it needs.

### Create a virtual environment

Think of this like creating a clean workspace just for this application:

```bash
uv venv --python python3.11
```

**What to expect:**
- You'll see messages about creating the environment
- This takes about 30 seconds
- A new folder called `.venv` is created (you won't see it in normal folders—it starts with a dot)

### Activate the environment

This tells your computer "use the workspace we just created":

**On macOS/Linux:**
```bash
source .venv/bin/activate
```

**On Windows:**
```bash
.venv\Scripts\activate
```

**What to expect:**
- Your terminal prompt will change—you'll see `(.venv)` at the beginning
- This means the environment is active!
- **IMPORTANT**: You need to activate this environment every time you open a new terminal to use the application

### Install the application and all its dependencies

```bash
uv pip install -e .
```

**What to expect:**
- Lots of text will scroll by showing packages being installed
- This takes 2-5 minutes
- You'll eventually see "Successfully installed..." messages

**What just happened?**
- `uv pip install` downloaded and installed all the code libraries the application needs
- `-e .` means "install from this folder in editable mode"

---

## Step 6: Configure Your API Keys

The application needs API keys to access AI services. Think of API keys like passwords that let the application use external services.

### Get your API keys

You'll need to sign up for these services and get API keys:

#### 1. Anthropic API Key (REQUIRED)

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Click "API Keys" in the left sidebar
4. Click "Create Key"
5. Copy the key (starts with `sk-ant-...`)

**Cost:** Claude charges per usage. Typical memo costs $1-5.

#### 2. Tavily API Key (RECOMMENDED)

1. Go to [tavily.com](https://tavily.com)
2. Sign up for a free account
3. Go to your dashboard
4. Copy your API key

**Cost:** Free tier includes 1,000 searches per month—plenty for getting started!

#### 3. Perplexity API Key (OPTIONAL)

1. Go to [perplexity.ai](https://www.perplexity.ai)
2. Sign up for API access
3. Get your API key from the dashboard

**Cost:** Pay-per-use for citations. About $0.75 per memo section.

### Set up your configuration file

1. **Copy the example configuration:**

```bash
cp .env.example .env
```

2. **Edit the configuration file:**

**On macOS:**
```bash
open -e .env
```
This opens the file in TextEdit.

**On Windows:**
```bash
notepad .env
```
This opens the file in Notepad.

**On Linux:**
```bash
nano .env
```
This opens the file in a text editor.

3. **Replace the placeholder text with your actual API keys:**

Find this:
```
ANTHROPIC_API_KEY=your-api-key-here
```

Replace with your actual key (keep no spaces around the =):
```
ANTHROPIC_API_KEY=sk-ant-api03-abc123xyz...
```

Do the same for:
```
TAVILY_API_KEY=tvly-abc123...
PERPLEXITY_API_KEY=pplx-abc123...
```

4. **Save the file and close it**

**On macOS/Windows:** Click File → Save, then close

**On Linux (nano):** Press `Ctrl + X`, then `Y`, then Enter

### Verify your setup

Let's make sure everything is configured correctly:

```bash
python3.11 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('✓ Config loaded!' if os.getenv('ANTHROPIC_API_KEY') else '✗ Missing ANTHROPIC_API_KEY')"
```

**What to expect:**
- ✅ `✓ Config loaded!` → Everything is set up correctly!
- ❌ `✗ Missing ANTHROPIC_API_KEY` → Check your .env file

---

## Step 7: Generate Your First Memo

Now the fun part—let's create an investment memo!

### Make sure your environment is activated

Check if you see `(.venv)` at the start of your terminal prompt.

**If not, activate it:**

**On macOS/Linux:**
```bash
source .venv/bin/activate
```

**On Windows:**
```bash
.venv\Scripts\activate
```

### Run the application

Let's generate a memo for a sample company:

```bash
python3.11 -m src.main "TheoryForge" --type direct --mode consider
```

**What each part means:**
- `python3.11 -m src.main` → Run the application
- `"TheoryForge"` → The company name (replace with any company)
- `--type direct` → This is a direct startup investment (use `fund` for LP commitments)
- `--mode consider` → We're considering investing (use `justify` if already invested)

**What to expect:**
- You'll see colorful progress messages showing what the AI is doing
- The process takes 5-15 minutes depending on complexity
- Messages like:
  - "🔍 Researching company..."
  - "✍️ Writing sections..."
  - "🔗 Adding citations..."
  - "✅ Validation complete"

### Find your memo

When complete, your memo will be in:
```
output/TheoryForge-v0.0.1/4-final-draft.md
```

**To see all your output files:**

**On macOS:**
```bash
open output/TheoryForge-v0.0.1/
```

**On Windows:**
```bash
explorer output\TheoryForge-v0.0.1
```

**On Linux:**
```bash
xdg-open output/TheoryForge-v0.0.1/
```

### Understanding the output

The folder contains:
- `1-research.md` → All the research findings
- `2-sections/` → Individual memo sections (10 files)
- `3-validation.md` → Quality score and feedback
- `4-final-draft.md` → **Your complete memo!**
- `state.json` → Technical details (for debugging)

---

## Step 8: Export Your Memo

The final memo is in Markdown format (`.md`). Let's convert it to formats you can share.

### Export to HTML (recommended)

**Light mode (for printing):**
```bash
python3.11 export-branded.py output/TheoryForge-v0.0.1/4-final-draft.md
```

**Dark mode (for screens):**
```bash
python3.11 export-branded.py output/TheoryForge-v0.0.1/4-final-draft.md --mode dark
```

**What to expect:**
- HTML file created in `exports/branded/`
- Opens beautifully in any web browser
- Includes full branding and citations
- Can be printed to PDF from browser

**To open the HTML file:**

**On macOS:**
```bash
open exports/branded/TheoryForge-v0.0.1.html
```

**On Windows:**
```bash
start exports/branded/TheoryForge-v0.0.1.html
```

**On Linux:**
```bash
xdg-open exports/branded/TheoryForge-v0.0.1.html
```

### Export to Word (.docx)

```bash
python3.11 md2docx.py output/TheoryForge-v0.0.1/4-final-draft.md
```

**What to expect:**
- Word file created in `exports/`
- Can be edited in Microsoft Word
- Note: Citations only render properly in Microsoft Word (not Google Docs)

### Export all memos at once

If you've generated multiple memos:

```bash
./export-all-modes.sh
```

This creates both light and dark HTML versions of all memos!

---

## Common Problems and Solutions

### Problem: "command not found"

**Possible causes:**
1. Tool not installed
2. Tool not in your PATH
3. Terminal needs to be restarted

**Solutions:**
- Re-run the installation steps for the missing tool
- Close and reopen your terminal
- On Windows, make sure you checked "Add to PATH" during Python installation

---

### Problem: "No module named 'dotenv'" or similar

**Cause:** Dependencies not installed or virtual environment not activated

**Solution:**
1. Activate your virtual environment:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```
2. Reinstall dependencies:
   ```bash
   uv pip install -e .
   ```

---

### Problem: "API key not found" or authentication errors

**Cause:** API keys not configured correctly in `.env` file

**Solution:**
1. Open your `.env` file
2. Check that keys are pasted correctly (no extra spaces)
3. Make sure the file is saved
4. Keys should look like:
   ```
   ANTHROPIC_API_KEY=sk-ant-api03-...
   TAVILY_API_KEY=tvly-...
   ```

---

### Problem: Dependencies keep disappearing

**Cause:** Wrong virtual environment or using `pip` instead of `uv`

**Solution:**
1. Delete all virtual environments:
   ```bash
   rm -rf .venv venv
   ```
2. Create fresh environment:
   ```bash
   uv venv --python python3.11
   ```
3. Activate it:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```
4. Install with uv (NOT pip):
   ```bash
   uv pip install -e .
   ```

**IMPORTANT:** Always use `uv pip install`, never `pip install`!

---

### Problem: "Permission denied" errors

**On macOS/Linux:**

Try adding `sudo` before the command:
```bash
sudo [command]
```

Or fix permissions:
```bash
chmod +x [file]
```

**On Windows:**

Right-click Command Prompt or PowerShell and select "Run as Administrator"

---

### Problem: Memo generation takes too long or times out

**Possible causes:**
1. Internet connection issues
2. API service slowness
3. Very complex company with lots of data

**Solutions:**
- Check your internet connection
- Try again later (API services may be busy)
- For huge memos, try improving sections individually (see below)

---

### Problem: Want to improve just one section

If only one section needs work, you don't need to regenerate the whole memo!

**Use the section improvement tool:**
```bash
python3.11 improve-section.py "TheoryForge" "Team"
```

**Available section names:**
- Executive Summary
- Business Overview
- Market Context
- Team
- Technology & Product
- Traction & Milestones
- Funding & Terms
- Risks & Mitigations
- Investment Thesis
- Recommendation

This only takes ~60 seconds and costs ~$0.75 instead of regenerating everything!

---

## Updating the Application

To get the latest features and bug fixes:

### 1. Save any work in progress

Make sure you've exported any memos you're working on.

### 2. Navigate to the application folder

```bash
cd ~/Documents/investment-memo-orchestrator
```

### 3. Download the latest code

```bash
git pull origin main
```

**What to expect:**
- If there are updates, you'll see files being downloaded
- If you're already up to date, it will say "Already up-to-date"

### 4. Update dependencies

```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

uv pip install -e .
```

**What to expect:**
- New or updated packages will be installed
- Takes 1-2 minutes

---

### 5. (macOS Only) Keep Your Tools Updated with Homebrew

**🎉 Mac users: Here's the beauty of Homebrew!**

To update ALL your Homebrew-installed tools (Python, Git, uv, and everything else) in one command:

```bash
brew update && brew upgrade
```

**What this does:**
- `brew update` → Updates Homebrew's list of available software
- `brew upgrade` → Updates all outdated software to latest versions

**Check what needs updating:**
```bash
brew outdated
```

This shows which tools have new versions available.

**Update specific tools only:**
```bash
brew upgrade python@3.11
brew upgrade git
brew upgrade uv
```

**Keep Homebrew itself healthy:**
```bash
brew doctor
```

This checks for any problems with your Homebrew installation and suggests fixes.

**Pro tip:** Run `brew update && brew upgrade` once a month to keep everything current! It takes 2-5 minutes and keeps all your development tools up to date automatically.

**Why this is amazing:**
- ✅ One command updates Python, Git, uv, and hundreds of other tools
- ✅ No need to visit websites and download installers
- ✅ No version conflicts or broken dependencies
- ✅ Homebrew handles everything safely

This is why we recommended installing Homebrew first! 🚀

---

## Getting Help

### Check the documentation

- **This guide**: `CASUAL_USER_GUIDE.md` (you're reading it!)
- **Technical guide**: `CLAUDE.md` (for developers)
- **Full documentation**: `README.md`

### Getting support

If you're stuck:

1. **Check Common Problems section above** (most issues are covered there)
2. **Contact your team administrator** or IT support
3. **Check the project's issue tracker** (if available)

### Useful debugging commands

If someone is helping you troubleshoot, they might ask you to run these:

**Check Python version:**
```bash
python3.11 --version
```

**Check what's installed:**
```bash
uv pip list
```

**Check if environment is active:**
```bash
which python
```

**View recent memo logs:**
```bash
cat output/*/state.json
```

---

## Quick Reference Card

**Bookmark this section for daily use!**

### Every time you use the application:

1. **Open Terminal**
2. **Navigate to folder:**
   ```bash
   cd ~/Documents/investment-memo-orchestrator
   ```
3. **Activate environment:**
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```
4. **Generate memo:**
   ```bash
   python3.11 -m src.main "Company Name" --type direct --mode consider
   ```
5. **Export to HTML:**
   ```bash
   python3.11 export-branded.py output/Company-v0.0.1/4-final-draft.md
   ```

### Common commands:

```bash
# Direct investment (prospective)
python3.11 -m src.main "Startup Name" --type direct --mode consider

# Direct investment (already invested)
python3.11 -m src.main "Startup Name" --type direct --mode justify

# Fund commitment (prospective)
python3.11 -m src.main "Fund Name" --type fund --mode consider

# Fund commitment (already invested)
python3.11 -m src.main "Fund Name" --type fund --mode justify

# Improve one section
python3.11 improve-section.py "Company Name" "Section Name"

# Export to HTML (light)
python3.11 export-branded.py output/Company-v0.0.1/4-final-draft.md

# Export to HTML (dark)
python3.11 export-branded.py output/Company-v0.0.1/4-final-draft.md --mode dark

# Export to Word
python3.11 md2docx.py output/Company-v0.0.1/4-final-draft.md
```

### Homebrew commands (macOS only):

```bash
# Update all tools installed via Homebrew
brew update && brew upgrade

# Check what's outdated
brew outdated

# Update specific tool
brew upgrade python@3.11

# Search for available packages
brew search [package-name]

# Install new tool
brew install [package-name]

# Uninstall tool
brew uninstall [package-name]

# Check Homebrew health
brew doctor

# List all installed packages
brew list
```

---

## Tips for Success

### 1. Keep your terminal open

Don't close the terminal while the application is running! You can minimize it, but closing it will stop the process.

### 2. Use exact company names

The application searches the web using the name you provide. Use the official company name for best results.

### 3. Review the validation score

After generation, check `3-validation.md` for the quality score (out of 10). Scores below 8 may need manual review.

### 4. Create company data files

For better results, create a JSON file in the `data/` folder with company details:

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "Brief company description",
  "url": "https://company.com",
  "stage": "Series B"
}
```

Save as `data/CompanyName.json`

### 5. Version control

The application automatically versions your memos (v0.0.1, v0.0.2, etc.). Each run creates a new version, so you never lose previous work!

### 6. (macOS) Keep tools updated with Homebrew

Run `brew update && brew upgrade` once a month to keep Python, Git, uv, and all other tools automatically updated. This prevents version conflicts and security issues!

---

## Congratulations!

You've successfully set up and used the Investment Memo Orchestrator! 🎉

Remember:
- ✅ Activate your virtual environment every time: `source .venv/bin/activate`
- ✅ Always use `uv pip install`, never `pip install`
- ✅ **(Mac users)** Keep tools updated with `brew update && brew upgrade`
- ✅ Check the [Common Problems section](#common-problems-and-solutions) if something goes wrong
- ✅ Bookmark the [Quick Reference Card](#quick-reference-card) for daily use

Happy memo writing!

---

*Last updated: 2025-11-20*
*For technical documentation, see CLAUDE.md*
