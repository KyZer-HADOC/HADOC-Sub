# HADOC Sub

HADOC Sub is a Windows desktop subtitle studio for translating English SRT files into Sinhala.

## Version 1.5.0

This release adds MyMemory Translation as a no-API-key English-to-Sinhala translation provider, plus automatic provider failover and resumable SRT progress.
Release v1.5.0 Windows build is available from the GitHub Releases page.

- Modern dark Windows desktop interface with maximized launch and F11 fullscreen.
- First-run API setup with encrypted provider credentials.
- Add translation providers to a provider pool: MyMemory Translation (no API key required), Google Gemini, Groq, NVIDIA NIM, OpenRouter Free, Cloudflare Workers AI, or any compatible custom chat-completions endpoint.
- Automatic provider failover: if an API returns 429, an authentication error, a network failure, or an invalid response, HADOC Sub tries the next configured provider.
- Smaller translation batches to reduce per-request token spikes.
- Saves progress after every successful batch.
- Resume support: reopen the same original SRT file and press Start translation; completed lines are skipped.
- Subtitle table with search, English/Sinhala preview, manual editing and UTF-8 SRT export.
- Original subtitle numbering and timestamps are preserved.

## First launch and provider setup

1. Run HADOC-Sub.exe.
2. Choose **MyMemory Translation**.
3. The service URL and language pair (`en-US|si-LK`) are filled in automatically. No API key is required.
4. Optionally enter an email address in the email field to increase the documented free daily allowance from 5,000 to 50,000 characters. You may leave it blank.
5. Click Test API, then Add to provider pool.
6. Click Save & Start HADOC Sub.
7. Open an English SRT and click Start translation.

Settings can be changed later from API Settings. API keys and optional provider emails are encrypted with Windows DPAPI and are bound to the Windows account that saved them.

## Provider presets

Google Gemini:
- API URL: https://generativelanguage.googleapis.com/v1beta/openai
- Default model: gemini-3.8-flash
- API key: https://aistudio.google.com/apikey

Groq:
- API URL: https://api.groq.com/openai/v1
- Default model: openai/gpt-oss-120b
- API key: https://console.groq.com/keys

NVIDIA NIM:
- API URL: https://integrate.api.nvidia.com/v1
- Default model: nvidia/nemotron-3.5-super-vl-120b-a12b
- API key: https://build.nvidia.com/explore/discover

OpenRouter Free:
- API URL: https://openrouter.ai/api/v1
- Default model: openrouter/free
- API key: https://openrouter.ai/settings/keys
- Free model variants are currently limited to 20 requests per minute and 50 requests per day; availability and provider limits can change.

MyMemory Translation:
- API URL: https://api.mymemory.translated.net
- Language pair: `en-US|si-LK`
- API key: not required.
- Optional email is sent as the `de` parameter to increase the daily allowance.
- The service accepts up to 500 bytes per translation segment; HADOC Sub splits unusually long subtitle entries before sending them.
- MyMemory's official limits are 5,000 characters/day anonymously or 50,000 characters/day with an email address. This is a quota, not unlimited usage.
- MyMemory is a translation-memory and machine-translation service; output may be less context-aware than a chat-based movie subtitle model. Review the first few lines before translating a full file.

Custom:
- Any provider that supports an OpenAI-compatible /chat/completions endpoint.

## Rate limits and failover

No free API is unlimited. Each provider enforces its own quotas. A pool lets the app switch to another configured service when one becomes unavailable; it does not increase the quota of a single provider account. Some provider limits are organization-wide, so adding extra keys within the same organization may not increase its quota.

If every configured provider fails, translation pauses and already completed batches stay saved. Add or restore a provider, reopen the same source SRT if needed, and click Start translation to continue only the untranslated lines.

## Download

Download HADOC-Sub.exe from the latest GitHub Release:
https://github.com/KyZer-HADOC/HADOC-Sub/releases

## Local build

Install Python 3.11 or newer, then run build.bat. The generated EXE is placed at dist\HADOC-Sub.exe.

The build installs requirements.txt, runs syntax checks and unit tests, then packages the application using PyInstaller.

Created by KyZer_HADOC.