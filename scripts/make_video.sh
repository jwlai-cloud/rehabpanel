#!/usr/bin/env bash
# Render the RehabPanel demo video from the LIVE coordinator app: boots the
# FastAPI backend, captures each view via headless Chrome, drives a sick->replan
# incident through the API, narrates (Alibaba CosyVoice if a key is set, else
# macOS `say`), burns subtitles, assembles with ffmpeg -> results/demo.mp4.
# macOS only (say + Chrome). Deterministic (offline engine).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
VOICE="${VOICE:-Samantha}"
PORT="${PORT:-8137}"
URL="http://localhost:$PORT"
BD="$ROOT/.videobuild"; rm -rf "$BD"; mkdir -p "$BD"; mkdir -p "$ROOT/results"
export REHABPANEL_OFFLINE=1

command -v ffmpeg >/dev/null || { echo "need ffmpeg"; exit 1; }
command -v say   >/dev/null || { echo "need macOS say"; exit 1; }
[ -x "$CHROME" ] || { echo "no Chrome at $CHROME"; exit 1; }

[ -f "$ROOT/results/gap.png" ] || { echo "== gap.png missing -> benchmark =="; python -m rehabpanel.benchmark >/dev/null; }

echo "== boot coordinator backend =="
(python -m uvicorn rehabpanel.api:app --port "$PORT" >/tmp/rehab_video.log 2>&1 &) ; sleep 5
trap 'pkill -f "uvicorn rehabpanel.api:app --port $PORT" 2>/dev/null || true' EXIT
curl -sf "$URL/api/state" >/dev/null || { echo "server not up"; cat /tmp/rehab_video.log; exit 1; }

shoot(){ "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1300,820 --default-background-color=FFFFFFFF \
  --screenshot="$2" --virtual-time-budget=3500 "$1" >/dev/null 2>&1; }

card(){ cat > "$BD/$1" <<HTML
<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:#eef3f7;color:#0f2942;
   font:400 28px/1.4 "Segoe UI",-apple-system,Arial,sans-serif}
 .wrap{height:720px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:18px;
   text-align:center;border-top:8px solid #0b6e63}
 h1{font-size:60px;margin:0;font-weight:800}.accent{color:#0b6e63}.sub{font-size:30px;color:#5a7287;max-width:960px}
 .foot{position:absolute;bottom:34px;width:100%;text-align:center;color:#5a7287;font-size:20px}
</style></head><body><div class="wrap">$2</div></body></html>
HTML
}
card title.html '<svg width="92" height="92" viewBox="0 0 28 28"><rect x="1" y="1" width="26" height="26" rx="7" fill="#e6f3f0" stroke="#0b6e63" stroke-width="1.5"/><path d="M4 15 H9 L11 9 L15 19 L17 13 H24" fill="none" stroke="#0b6e63" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><h1>Rehab<span class="accent">Panel</span></h1><div class="sub">An AI <b>agent society</b> assisting a nurse coordinator</div><div class="foot">Qwen Cloud · Track 3 · synthetic data</div>'
card closing.html '<h1 class="accent">Negotiate. Adapt. Explain.</h1><div class="sub">Five advocates + a referee, re-planning under disruption with minimal churn.<br>All Qwen, deployed on Alibaba Cloud · decision support on synthetic data.</div><div class="foot">github.com/jwlai-cloud/rehabpanel · MIT</div>'

echo "== capture initial-state frames =="
shoot "file://$BD/title.html"            "$BD/01.png"
shoot "$URL/#caseload"                    "$BD/02.png"
shoot "$URL/#team"                        "$BD/03.png"
shoot "$URL/#rules"                       "$BD/04.png"
shoot "$URL/?r=0#schedule"                "$BD/05.png"
shoot "$URL/?r=99#schedule"               "$BD/06.png"
echo "== incident: nurse sick =="
curl -sf -X POST "$URL/api/incident/sick" >/dev/null
shoot "$URL/#kpis"                         "$BD/07.png"
echo "== re-plan (warm) =="
curl -sf -X POST "$URL/api/replan" >/dev/null
shoot "$URL/?r=99#schedule"               "$BD/08.png"
shoot "$URL/#kpis"                         "$BD/09.png"
shoot "file://$BD/closing.html"           "$BD/11.png"

IMGS=( "$BD/01.png" "$BD/02.png" "$BD/03.png" "$BD/04.png" "$BD/05.png" "$BD/06.png" \
       "$BD/07.png" "$BD/08.png" "$BD/09.png" "$ROOT/results/gap.png" "$BD/11.png" )
# crop top for app views (action lives up top); fit+pad for cards/gap
CROP=( card app app app app app app app app gap card )
NARR=(
"RehabPanel — an AI agent society assisting a nurse coordinator."
"A coordinator has 56 patients due but only 43 slots this week."
"Across three nurses — acuity, overdue dates, continuity and preference all compete for the same time."
"This is the priority rule the society optimizes. It's causal: drop continuity to zero and the agents stop protecting primary-nurse matches."
"Watch them negotiate. The acuity-first draft scores minus 141 — no better than a single agent."
"Five advocates object; the charge-nurse referee resolves one conflict per round and logs each. Value climbs to minus 70 — a 71 point gain."
"Then reality breaks: a nurse calls in sick on Tuesday. The score drops to minus 106 and patients are orphaned."
"Re-plan runs a warm negotiation that repairs only what the incident broke."
"Just 4 of 39 appointments change, and the session timeline recovers. That is the measurable efficiency."
"Across 25 seeded runs the society wins every time, and the advantage widens as slots get scarcer."
"All Qwen, deployed on Alibaba Cloud. Decision support on fully synthetic data."
)
SUBS=(
"RehabPanel — an agent society\nassisting a nurse coordinator"
"56 patients due · only 43 slots this week"
"3 nurses — acuity, overdue, continuity\nand preference compete for the time"
"The priority rule is causal: zero continuity\n→ agents stop protecting primary-nurse matches"
"Acuity-first draft = -141\n(no better than a single agent)"
"5 advocates object, referee rules one\nconflict/round → value -141 → -70 (+71)"
"Nurse sick Tuesday → score drops to -106,\npatients orphaned"
"Re-plan: a warm negotiation repairs\nonly what broke"
"4 of 39 appointments change;\nthe timeline recovers — minimal disruption"
"25 runs: society wins every time,\nwidening with scarcity"
"All Qwen on Alibaba Cloud ·\ndecision support · synthetic data"
)

echo "== narrate + build scene clips =="
SRT="$BD/demo.srt"; : > "$SRT"; > "$BD/concat.txt"; t0=0; idx=1; VOICEMODE="say"
ff(){ awk -v s="$1" 'BEGIN{printf "%02d:%02d:%06.3f",int(s/3600),int((s%3600)/60),s-int(s/60)*60}' | sed 's/\./,/'; }
for i in "${!IMGS[@]}"; do
  n=$(printf "%02d" $((i+1)))
  if python scripts/tts.py "${NARR[$i]}" "$BD/a$n.mp3" >/dev/null 2>&1; then AUD="$BD/a$n.mp3"; VOICEMODE="cosyvoice";
  else say -v "$VOICE" -o "$BD/a$n.aiff" "${NARR[$i]}"; AUD="$BD/a$n.aiff"; fi
  dur=$(ffprobe -v quiet -of csv=p=0 -show_entries format=duration "$AUD"); len=$(awk -v d="$dur" 'BEGIN{print d+0.8}')
  case "${CROP[$i]}" in
    app)  VF="crop=2600:1440:0:0,scale=1280:720" ;;
    gap)  VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=white" ;;
    *)    VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xeef3f7" ;;
  esac
  ffmpeg -y -loop 1 -t "$len" -i "${IMGS[$i]}" -i "$AUD" -vf "$VF,fps=30,format=yuv420p" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 44100 -af apad -t "$len" "$BD/scene$n.mp4" >/dev/null 2>&1
  echo "file 'scene$n.mp4'" >> "$BD/concat.txt"
  st=$(ff "$t0"); en=$(ff "$(awk -v a="$t0" -v l="$len" 'BEGIN{print a+l-0.15}')")
  printf '%d\n%s --> %s\n%b\n\n' "$idx" "$st" "$en" "${SUBS[$i]}" >> "$SRT"
  t0=$(awk -v a="$t0" -v l="$len" 'BEGIN{print a+l}'); idx=$((idx+1)); echo "  scene $n: ${dur}s"
done

echo "== concat + burn subtitles =="
( cd "$BD" && ffmpeg -y -f concat -safe 0 -i concat.txt -c copy raw.mp4 >/dev/null 2>&1 )
ffmpeg -y -i "$BD/raw.mp4" -vf "subtitles=$BD/demo.srt:force_style='Fontname=Arial,FontSize=20,PrimaryColour=&H00FFFFFF&,BorderStyle=4,BackColour=&HB0000000&,Outline=0,Shadow=0,MarginV=36,Alignment=2'" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac "$ROOT/results/demo.mp4" >/dev/null 2>&1
dur=$(ffprobe -v quiet -of csv=p=0 -show_entries format=duration "$ROOT/results/demo.mp4")
echo "== done: results/demo.mp4 (${dur}s) · voice: $VOICEMODE =="
