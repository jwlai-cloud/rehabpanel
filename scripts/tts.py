"""Neural TTS via Alibaba DashScope CosyVoice — keeps narration on Qwen Cloud.

Usage: python scripts/tts.py "text" out.mp3
Exit 0 + write file on success; non-zero on no-key / missing SDK / API error so
the caller (make_video.sh) falls back to macOS `say`. Needs `pip install dashscope`.

Env: TTS_VOICE (default longxiaochun), TTS_MODEL (default cosyvoice-v1),
REHABPANEL_INTL=1 uses the Singapore (dashscope-intl) endpoint to match qwen_client.
"""
import os
import sys


def main():
    if len(sys.argv) != 3:
        sys.exit(2)
    text, out = sys.argv[1], sys.argv[2]
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit(3)  # no key -> caller uses `say`
    try:
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
    except ImportError:
        sys.stderr.write("tts: `pip install dashscope` for neural voice; using say\n")
        sys.exit(4)
    try:
        if os.environ.get("REHABPANEL_INTL", "1") == "1":
            dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"
        dashscope.api_key = key
        synth = SpeechSynthesizer(
            model=os.environ.get("TTS_MODEL", "cosyvoice-v1"),
            voice=os.environ.get("TTS_VOICE", "longxiaochun"),
            format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
        )
        audio = synth.call(text)
        if not audio:
            sys.exit(5)
        with open(out, "wb") as f:
            f.write(audio)
        print("cosyvoice")
    except Exception as e:  # any transport/auth/model error -> fall back to say
        sys.stderr.write(f"tts fallback ({e})\n")
        sys.exit(6)


if __name__ == "__main__":
    main()
