# HADOC Sub

HADOC Sub is a Windows desktop subtitle studio that can generate subtitles directly from videos and translate English SRT files into Sinhala.

## Version 1.7.4

Version 1.7.4 keeps the repository-root icon.jpg embedded as the EXE, window, and taskbar icon. The Windows build now runs a post-build one-file extraction smoke test that verifies the ICO resource and bundled FFmpeg can be extracted and FFmpeg can launch. UPX/LZMA compression remains enabled for eligible inner binaries and FFmpeg while Windows Control Flow Guard protection is preserved. Version 1.7.0 added automatic video-to-subtitle generation using Groq Whisper, bundled FFmpeg audio extraction, timestamped English SRT export, and automatic Sinhala translation. Existing SRT translation, provider failover, and checkpoint/resume are preserved.

### Generate Sinhala subtitles from a video

1. Run HADOC-Sub.exe and configure a translation provider such as Google Translate (Fast).
2. Open **API Settings**, select **Groq**, enter a Groq API key, add it to the provider pool, and save.
3. Click **Open Video** and choose an MP4, MKV, AVI, MOV, M4V, WEBM, WMV or FLV file.
4. Click **Generate Sinhala Subtitles**. HADOC Sub extracts audio with its bundled FFmpeg, transcribes it with Groq Whisper in short audio chunks, creates timestamped English captions, then starts the existing English-to-Sinhala translation automatically.
5. The English transcript is saved beside the video as `<video>_en.srt`. After review, click **Save SRT** to export `<video>_si.srt`.

Video transcription currently expects English speech. A Groq API key is required; the transcription request is subject to the current limits and pricing of your Groq account. For the free tier, HADOC Sub uses 8-minute mono 16 kHz FLAC chunks to keep upload sizes much smaller than WAV and below the documented 25 MB upload limit in typical use. Temporary connection failures are retried automatically. The app resumes translation from its saved checkpoint if interrupted. Video audio is uploaded to Groq for transcription; it is not processed entirely offline.



This release adds batched Google Translate Web requests as the fast first-choice translator, automatically adds MyMemory as a no-API-key fallback, and caches repeated MyMemory subtitle lines during the session.
MyMemory is automatically added as a backup provider when Google Translate is selected.
The optimized v1.7.4 Windows build is available from the GitHub Releases page.

- Modern dark Windows desktop interface with maximized launch and F11 fullscreen.
- First-run API setup with encrypted provider credentials.
- Add translation providers to a provider pool: Google Translate Web (batched, no API key), MyMemory Translation (no API key), Google Gemini, Groq, NVIDIA NIM, OpenRouter Free, Cloudflare Workers AI, or any compatible custom chat-completions endpoint.
- Automatic provider failover: if an API returns 429, an authentication error, a network failure, or an invalid response, HADOC Sub tries the next configured provider.
- Smaller translation batches to reduce per-request token spikes.
- Saves progress after every successful batch.
- Resume support: reopen the same original SRT file and press Start translation; completed lines are skipped.
- Subtitle table with search, English/Sinhala preview, manual editing and UTF-8 SRT export.
- Original subtitle numbering and timestamps are preserved.

## First launch and provider setup

1. Run HADOC-Sub.exe.
2. Choose **Google Translate (Fast)**.
3. The endpoint and language pair (`en|si`) are filled in automatically. No API key is required.
4. Click Test API, then Add to provider pool.
5. Click Save & Start HADOC Sub. MyMemory is automatically added as the fallback.
6. To increase MyMemory's daily allowance, open API Settings, select MyMemory Translation, and optionally enter an email address.

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

Google Translate (Fast):
- Endpoint: https://translate.googleapis.com/translate_a/t
- Language pair: `en|si`
- API key: not required.
- Sends several subtitle lines as repeated `q` parameters in one request, reducing round trips compared with one request per subtitle line.
- This is an unofficial Google Translate web endpoint, not the paid/official Cloud Translation API. It has no published quota or SLA and can be rate-limited or changed by Google. HADOC Sub falls back to MyMemory when the endpoint fails.

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