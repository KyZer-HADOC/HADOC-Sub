# HADOC Sub

HADOC Sub is a Windows desktop subtitle studio for translating English SRT files into Sinhala.

## Version 1.4.0

This release adds a dedicated Cloudflare Workers AI translation provider with automatic failover and resumable SRT progress.
Release v1.4.0 Windows build is available from the GitHub Releases page.

- Modern dark Windows desktop interface with maximized launch and F11 fullscreen.
- First-run API setup with encrypted provider credentials.
- Add multiple AI providers to a provider pool: Google Gemini, Groq, NVIDIA NIM, OpenRouter Free, Cloudflare Workers AI (Meta M2M100), or any compatible custom chat-completions endpoint.
- Automatic provider failover: if an API returns 429, an authentication error, a network failure, or an invalid response, HADOC Sub tries the next configured provider.
- Smaller translation batches to reduce per-request token spikes.
- Saves progress after every successful batch.
- Resume support: reopen the same original SRT file and press Start translation; completed lines are skipped.
- Subtitle table with search, English/Sinhala preview, manual editing and UTF-8 SRT export.
- Original subtitle numbering and timestamps are preserved.

## First launch and provider setup

1. Run HADOC-Sub.exe.
2. Choose a provider preset such as Google Gemini, Groq or Cloudflare Workers AI.
3. Enter that provider's API URL, model and API key/token. For Cloudflare, replace `ACCOUNT_ID` in the preset URL with your Cloudflare Account ID.
4. Click Test API, then Add to provider pool.
5. Add other providers one at a time.
6. Click Save & Start HADOC Sub.
7. Open an English SRT and click Start translation.

Settings can be changed later from API Settings. API keys are encrypted with Windows DPAPI and are bound to the Windows account that saved them.

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

Cloudflare Workers AI:
- API URL: https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/run
- Replace `ACCOUNT_ID` with the Account ID shown on the Cloudflare Workers AI REST API page.
- Model: `@cf/meta/m2m100-1.2b`
- API key: a Cloudflare Workers AI API token with Workers AI access.
- The app requests English (`en`) to Sinhala (`si`) translation. The model supports Sinhala.
- Subtitle entries are sent as individual requests, with up to four requests in parallel. This dedicated translation model does not follow movie-context or dialogue-style instructions like a chat LLM, so review a short sample before translating a full movie.
- Cloudflare Workers AI Free includes a daily allocation of 10,000 Neurons. This is a quota, not unlimited usage; usage can pause when the allocation is exhausted.

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