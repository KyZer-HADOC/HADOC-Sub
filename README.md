# HADOC Sub

HADOC Sub is a Windows desktop application that translates English SubRip subtitle files (SRT) into natural Sinhala while preserving subtitle numbers and timestamps.

## Current version: 1.0.0

- Windows 10 and Windows 11 desktop GUI.
- Opens UTF-8 and common Windows-encoded SRT files.
- Translates subtitle entries in small batches through an OpenAI-compatible chat-completions API.
- Groq is preconfigured as the default provider. The API URL and model name are editable.
- Shows English and Sinhala subtitle text in a review table.
- Lets you edit individual Sinhala subtitle entries.
- Exports a UTF-8 SRT file with original subtitle numbering and timestamps.
- Remembers the API URL and model, but never saves the API key.
- Uses Python's built-in Tkinter and standard library. No extra runtime packages are needed when running from source.

## Download the Windows EXE

1. Open the repository's Actions tab.
2. Choose the workflow named Build HADOC Sub for Windows.
3. Click Run workflow, or open the latest automatic build triggered by a push to main.
4. When the run succeeds, open it and download the HADOC-Sub-Windows artifact.
5. Extract the ZIP archive and run HADOC-Sub.exe.

The workflow builds a standalone Windows executable using PyInstaller.

## Build locally on Windows

Install Python 3.11 or newer, then double-click build.bat or run it from PowerShell.

The output executable will be created at:

dist\HADOC-Sub.exe

## Translation API setup

HADOC Sub uses an OpenAI-compatible chat-completions endpoint.

Default provider settings:
- API base URL: https://api.groq.com/openai/v1
- Model: openai/gpt-oss-120b

Create an API key with your chosen provider, enter it in the API KEY field, open an SRT file, and click Translate to Sinhala. Provider model availability, rate limits, and any costs are controlled by that provider. Another compatible provider can be used by changing the API base URL and model.

Privacy notes:
- The API key stays in memory during the current app session only.
- The API key is not written to the settings file.
- Subtitle text is sent to the API provider you configure for translation.

## Important

- Subtitle numbering and timestamps are kept when saving.
- The app checks that the model returned every requested subtitle item. Missing items trigger an error instead of silently shifting subtitles.
- Any untranslated entries are preserved in the exported file, so review the translation before using it.
- This first tool translates existing SRT files. Audio transcription and creating subtitles when no SRT exists are planned as a separate tool.

Created by KyZer_HADOC.
