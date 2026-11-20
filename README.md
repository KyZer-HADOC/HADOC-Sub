# HADOC Sub

HADOC Sub is a Windows desktop subtitle studio for translating English SRT files into natural Sinhala.

## Version 1.1.0

- Modern dark desktop interface built with CustomTkinter.
- Opens maximized by default. Press F11 for true fullscreen and Esc to leave it.
- First launch opens an API setup screen. Save the API details once to continue to the subtitle studio.
- Google Gemini is the default provider. Groq and custom OpenAI-compatible providers are also supported.
- Test the API connection before saving.
- Provider, API URL, model name and encrypted API key are saved for the current Windows account.
- API keys are encrypted with Windows DPAPI; they are not stored as plain text.
- Opens UTF-8 and common Windows-encoded SRT files.
- Translates in small batches, preserving numbering and timestamps.
- Shows English and Sinhala rows for review. Individual Sinhala lines can be edited.
- Exports a UTF-8 Sinhala SRT file.

## First launch

1. Run HADOC-Sub.exe.
2. Choose Google Gemini (recommended default), Groq or Custom.
3. Enter the API base URL, model and API key.
4. Use Test API connection to check the details.
5. Click Save & Start HADOC Sub.
6. In the studio, open an English SRT, click Start translation, review the output and save the Sinhala SRT.

Settings can be changed later from API Settings or the Settings button.

## Gemini defaults

API base URL:
https://generativelanguage.googleapis.com/v1beta/openai

Model:
gemini-3.5-flash-lite

Create a key:
https://aistudio.google.com/apikey

Gemini API quotas and free-tier availability depend on the Google AI Studio project and can change. Check the current limits in Google AI Studio. An API key is required; subtitle text is sent to the provider you configure.

## Other providers

Groq preset:
- API base URL: https://api.groq.com/openai/v1
- Model: openai/gpt-oss-120b

Custom providers must support an OpenAI-compatible /chat/completions endpoint.

## Download the Windows EXE

Open the Releases page and download HADOC-Sub.exe from the latest release:
https://github.com/KyZer-HADOC/HADOC-Sub/releases

## Build locally on Windows

Install Python 3.11 or newer, then double-click build.bat. The generated EXE is placed in dist\HADOC-Sub.exe.

The build installs dependencies from requirements.txt, runs syntax checks and SRT parser tests, then packages the desktop app using PyInstaller.

## Notes

- Subtitle numbering and timestamps are preserved.
- If a provider rejects a batch or omits subtitle rows, the app reports an error instead of silently shifting subtitles.
- Entries not translated are preserved as original English. Review before using the exported subtitle file.
- API key encryption uses Windows DPAPI and is tied to the Windows user account that saved it.
- This release translates existing SRT files. Audio transcription and subtitle generation without an SRT file will be a separate tool.

Created by KyZer_HADOC.
