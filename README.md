# HADOC Sub

HADOC Sub is a Windows desktop subtitle studio for translating English SRT files into natural Sinhala.

## Version 1.2.0

- Modern dark Windows desktop interface with maximized launch and F11 fullscreen.
- Gemini is the default provider; Groq and custom OpenAI-compatible providers are supported.
- First-launch API setup screen with connection test and secure settings.
- API key is encrypted with Windows DPAPI and stored for the current Windows user.
- Main studio has always-visible Open SRT, Start translation and Save SRT actions.
- Larger subtitle table with search, English/Sinhala preview and manual editing.
- Opens UTF-8 and common Windows-encoded SRT files.
- Translates in batches while preserving subtitle numbering and timestamps.
- Exports UTF-8 Sinhala SRT files.

## First launch

1. Run HADOC-Sub.exe.
2. Choose Google Gemini, Groq or Custom.
3. Enter the API URL, model name and API key.
4. Click Test API connection to check the details.
5. Click Save & Start HADOC Sub.
6. In the studio, open an English SRT, click Start translation, review the Sinhala lines and save the result.

Settings can be changed later from API Settings or the Settings button.

## Gemini defaults

API base URL:
https://generativelanguage.googleapis.com/v1beta/openai

Model:
gemini-3.5-flash-lite

Create a key:
https://aistudio.google.com/apikey

Gemini API quotas and free-tier availability depend on the Google AI Studio project and can change. Check current limits in Google AI Studio. Subtitle text is sent to the configured provider for translation.

## Other providers

Groq preset:
- API base URL: https://api.groq.com/openai/v1
- Model: openai/gpt-oss-120b

Custom providers must support an OpenAI-compatible /chat/completions endpoint.

## Download

Download HADOC-Sub.exe from the latest GitHub Release:
https://github.com/KyZer-HADOC/HADOC-Sub/releases

## Local build

Install Python 3.11 or newer, then double-click build.bat. The generated executable is placed at dist\HADOC-Sub.exe.

The build installs requirements, runs syntax checks and SRT parser tests, then packages the app with PyInstaller.

## Notes

- Subtitle numbering and timestamps are preserved.
- If the provider rejects a batch or omits subtitle rows, the app reports an error rather than silently shifting subtitles.
- Untranslated entries remain in English; review the output before using it.
- API key encryption uses Windows DPAPI and is tied to the Windows account that saved it.
- This release translates existing SRT files. Audio transcription and generating subtitles without an SRT are a separate future tool.

Created by KyZer_HADOC.
