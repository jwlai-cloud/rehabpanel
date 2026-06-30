#!/usr/bin/env bash
# Render the RehabPanel demo video: frames from the live scrub UI + macOS AI
# voice (say) + burned subtitles -> results/demo.mp4. macOS only (say + Chrome).
# Deterministic: regenerates the seed-7 / ratio-1.3 run first.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
VOICE="${VOICE:-Samantha}"
PORT="${PORT:-8129}"
BD="$ROOT/.videobuild"; rm -rf "$BD"; mkdir -p "$BD"
mkdir -p "$ROOT/results"

command -v ffmpeg >/dev/null || { echo "need ffmpeg"; exit 1; }
command -v say   >/dev/null || { echo "need macOS say"; exit 1; }
[ -x "$CHROME" ] || { echo "no Chrome at $CHROME"; exit 1; }

echo "== regenerate seed-7 ratio-1.3 run =="
export REHABPANEL_OFFLINE=1
python -m rehabpanel.generator --seed 7 --ratio 1.3 >/dev/null
python -m rehabpanel.baseline --seed 7 >/dev/null
python -m rehabpanel.society.orchestrator --seed 7 >/dev/null
python -m rehabpanel.ui_export >/dev/null

echo "== build frame.html (param-driven, autoplay off) =="
python - "$BD" <<'PY'
import re, sys, pathlib
bd = pathlib.Path(sys.argv[1])
html = pathlib.Path("ui/index.html").read_text()
state = pathlib.Path("ui/state.json").read_text()
style = re.search(r"<style>.*?</style>", html, re.DOTALL).group(0)
body  = re.search(r"<body>(.*?)<script>", html, re.DOTALL).group(1)
script= re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
script = re.sub(r"fetch\('state\.json'\).*?\n\}\);", "init(EMBEDDED_STATE);", script, flags=re.DOTALL)
script += "\n(function(){var p=new URLSearchParams(location.search).get('r');if(p!==null)setRound(+p);})();"
(bd/"frame.html").write_text('<!doctype html><meta charset="utf-8">\n'+style+"\n"+body+"\n<script>\nconst EMBEDDED_STATE = "+state+";\n"+script+"</script>\n")
print("frame.html ok")
PY

card () { # $1 outfile  $2 inner-html
  cat > "$BD/$1" <<HTML
<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{margin:0;width:1280px;height:720px;overflow:hidden;
   background:#eef3f7;color:#0f2942;font:400 28px/1.4 "Segoe UI",-apple-system,Arial,sans-serif}
 .wrap{height:720px;display:flex;flex-direction:column;justify-content:center;align-items:center;
   gap:18px;text-align:center;border-top:8px solid #0b6e63}
 h1{font-size:64px;margin:0;font-weight:800;letter-spacing:-.02em}
 .accent{color:#0b6e63}
 .sub{font-size:30px;color:#5a7287;max-width:920px}
 .foot{position:absolute;bottom:34px;width:100%;text-align:center;color:#5a7287;font-size:20px}
</style></head><body><div class="wrap">$2</div></body></html>
HTML
}
card title.html '<svg width="92" height="92" viewBox="0 0 28 28"><rect x="1" y="1" width="26" height="26" rx="7" fill="#e6f3f0" stroke="#0b6e63" stroke-width="1.5"/><path d="M4 15 H9 L11 9 L15 19 L17 13 H24" fill="none" stroke="#0b6e63" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><h1>Rehab<span class="accent">Panel</span></h1><div class="sub">A multi-agent <b>Agent Society</b> for rehab patient scheduling</div><div class="foot">Qwen Cloud · Track 3 · synthetic data</div>'
card closing.html '<h1 class="accent">Negotiation beats a single pass</h1><div class="sub">Decision support on fully synthetic data.<br>All Qwen models, deployed on Alibaba Cloud.</div><div class="foot">github.com/jwlai-cloud/rehabpanel · MIT</div>'

echo "== serve build dir =="
(python -m http.server --directory "$BD" "$PORT" >/dev/null 2>&1 &) ; sleep 1
trap 'pkill -f "http.server --directory $BD $PORT" 2>/dev/null || true' EXIT

shoot () { # $1 url  $2 out.png
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size=1280,760 --default-background-color=FFFFFFFF \
    --screenshot="$2" --virtual-time-budget=2500 "$1" >/dev/null 2>&1
}

echo "== capture frames =="
shoot "http://localhost:$PORT/title.html"   "$BD/s1.png"
for r in 0 2 4 6 9; do shoot "http://localhost:$PORT/frame.html?r=$r" "$BD/cal_$r.png"; done
shoot "http://localhost:$PORT/closing.html" "$BD/s8.png"

# scene image list (in order) and matching narration
IMGS=( "$BD/s1.png" "$BD/cal_0.png" "$BD/cal_2.png" "$BD/cal_4.png" "$BD/cal_6.png" "$BD/cal_9.png" "$ROOT/results/gap.png" "$BD/s8.png" )
NARR=(
"RehabPanel — a multi-agent society for rehab scheduling, running on Qwen Cloud."
"A rehab nurse has 43 slots but 56 patients due. A single agent fills by acuity and abandons continuity. Baseline value: minus 141."
"Now the society negotiates. Five advocates raise objections, and the charge-nurse referee resolves one conflict per round."
"Each ruling moves a patient back to their primary clinician, and the plan's value climbs."
"Every swap stays capacity feasible. Continuity breaks fall from thirty toward thirteen."
"After negotiation the value reaches minus 70 — a 71 point gain a single agent never finds."
"Across 25 runs the society wins every time, and the advantage grows as slots get scarcer. The conflict is the point."
"Decision support on synthetic data. All Qwen, deployed on Alibaba Cloud."
)
SUBS=(
"RehabPanel — a multi-agent society for\nrehab scheduling, on Qwen Cloud."
"43 slots, 56 patients due. A single agent fills\nby acuity, abandons continuity. Baseline: -141."
"The society negotiates: 5 advocates object,\nthe referee resolves one conflict per round."
"Each ruling returns a patient to their\nprimary clinician — value climbs."
"Every swap stays capacity-feasible.\nContinuity breaks fall 30 -> 13."
"After negotiation: value -70 — a +71 gain\na single agent never finds."
"25 runs: the society wins every time,\nand the gap grows as slots get scarcer."
"Decision support on synthetic data.\nAll Qwen, deployed on Alibaba Cloud."
)

echo "== narrate + build scene clips =="
> "$BD/concat.txt"
SRT="$BD/demo.srt"; : > "$SRT"
t0=0; idx=1
ff () { awk -v s="$1" 'BEGIN{h=int(s/3600);m=int((s%3600)/60);sec=s-int(s/60)*60;printf "%02d:%02d:%06.3f",h,m,sec}' | sed 's/\./,/'; }
VOICEMODE="say"
for i in "${!IMGS[@]}"; do
  n=$((i+1))
  # neural CosyVoice (Alibaba) if a key is present; else macOS say
  if python scripts/tts.py "${NARR[$i]}" "$BD/a$n.mp3" >/dev/null 2>&1; then
    AUD="$BD/a$n.mp3"; VOICEMODE="cosyvoice"
  else
    say -v "$VOICE" -o "$BD/a$n.aiff" "${NARR[$i]}"; AUD="$BD/a$n.aiff"
  fi
  dur=$(ffprobe -v quiet -of csv=p=0 -show_entries format=duration "$AUD")
  pad=0.8; len=$(awk -v d="$dur" -v p="$pad" 'BEGIN{print d+p}')
  # normalize each source image to 1280x720: calendar frames crop top, others fit+pad
  case "${IMGS[$i]}" in
    *cal_*) VF="crop=2560:1440:0:0,scale=1280:720" ;;
    *gap.png) VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=white" ;;
    *) VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xeef3f7" ;;
  esac
  ffmpeg -y -loop 1 -t "$len" -i "${IMGS[$i]}" -i "$AUD" \
    -vf "$VF,fps=30,format=yuv420p" -c:v libx264 -pix_fmt yuv420p \
    -c:a aac -ar 44100 -af "apad" -t "$len" "$BD/scene$n.mp4" >/dev/null 2>&1
  echo "file 'scene$n.mp4'" >> "$BD/concat.txt"
  # srt entry
  st=$(ff "$t0"); en=$(ff "$(awk -v a="$t0" -v l="$len" 'BEGIN{print a+l-0.15}')")
  printf '%d\n%s --> %s\n%b\n\n' "$idx" "$st" "$en" "${SUBS[$i]}" >> "$SRT"
  t0=$(awk -v a="$t0" -v l="$len" 'BEGIN{print a+l}'); idx=$((idx+1))
  echo "  scene $n: ${dur}s"
done

echo "== concat + burn subtitles =="
( cd "$BD" && ffmpeg -y -f concat -safe 0 -i concat.txt -c copy raw.mp4 >/dev/null 2>&1 )
ffmpeg -y -i "$BD/raw.mp4" -vf "subtitles=$BD/demo.srt:force_style='Fontname=Arial,FontSize=20,PrimaryColour=&H00FFFFFF&,BorderStyle=4,BackColour=&HB0000000&,Outline=0,Shadow=0,MarginV=36,Alignment=2'" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac "$ROOT/results/demo.mp4" >/dev/null 2>&1

dur=$(ffprobe -v quiet -of csv=p=0 -show_entries format=duration "$ROOT/results/demo.mp4")
echo "== done: results/demo.mp4 (${dur}s) · voice: $VOICEMODE =="
