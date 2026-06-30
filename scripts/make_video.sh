#!/usr/bin/env bash
# Render the RehabPanel demo video (~3 min) from the LIVE coordinator app, with
# why/how narrative cards interleaved with live-app beats. Boots the FastAPI
# backend, captures each view via headless Chrome, drives a sick->replan incident
# through /api, narrates (Alibaba CosyVoice if a key is set, else macOS `say`),
# burns subtitles, assembles with ffmpeg -> results/demo.mp4. macOS only.
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

HEAD='<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:#eef3f7;color:#0f2942;
   font:400 28px/1.5 "Segoe UI",-apple-system,Arial,sans-serif}
 .c{height:720px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:18px;
   text-align:center;border-top:8px solid #0b6e63}
 .l{height:720px;display:flex;flex-direction:column;justify-content:center;gap:22px;padding:0 110px;border-top:8px solid #0b6e63}
 h1{font-size:52px;margin:0;font-weight:800}.accent{color:#0b6e63}
 .sub{font-size:30px;color:#5a7287;max-width:980px}
 .body{font-size:29px;color:#1f3b56;max-width:1010px}.body ul{margin:0;padding-left:26px}.body li{margin:11px 0}.body b{color:#0f2942}
 .foot{position:absolute;bottom:34px;left:0;width:100%;text-align:center;color:#5a7287;font-size:20px}
</style></head><body>'
ctr(){ printf '%s<div class="c">%s</div></body></html>' "$HEAD" "$2" > "$BD/$1"; }   # centered card
lft(){ printf '%s<div class="l"><h1 class="accent">%s</h1><div class="body">%s</div></div></body></html>' "$HEAD" "$2" "$3" > "$BD/$1"; }  # heading + body

ctr title.html '<svg width="92" height="92" viewBox="0 0 28 28"><rect x="1" y="1" width="26" height="26" rx="7" fill="#e6f3f0" stroke="#0b6e63" stroke-width="1.5"/><path d="M4 15 H9 L11 9 L15 19 L17 13 H24" fill="none" stroke="#0b6e63" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><h1>Rehab<span class="accent">Panel</span></h1><div class="sub">An AI <b>agent society</b> that helps a nurse coordinator plan the week</div><div class="foot">Qwen Cloud · Track 3: Agent Society · synthetic data</div>'
lft problem.html 'The problem' '<ul><li>Each cycle a rehab nurse decides <b>who to follow up, when, and how</b> — under fixed clinician time.</li><li>Acuity, overdue dates, continuity, capacity and preference <b>compete for the same scarce slots</b>.</li><li>Demand usually exceeds capacity — and the call lives in <b>one persons head</b>.</li></ul>'
lft why.html 'Why a society, not one agent' '<div>A single scheduling agent <b>collapses the trade-off</b> — it anchors on the most legible objective, acuity, fills greedily, and lets overdue patients and continuity quietly rot.<br><br>We make the conflict <b>explicit, and negotiated</b>.</div>'
lft how.html 'How it works' '<ul><li><b>Five advocates</b>, each arguing one objective: priority · window · continuity · capacity · preference.</li><li>A <b>charge-nurse referee</b> resolves one conflict at a time and logs every ruling.</li><li>A <b>pure-Python scorer</b> (never an LLM) grades each plan — reproducible.</li></ul>'
lft scope.html 'Honest scope' '<div><b>Decision support, not autonomous scheduling</b> — a human approves every plan.<br><br>All data is <b>fully synthetic</b>. No real patient records, ever.</div>'
ctr closing.html '<h1 class="accent">Negotiate. Adapt. Explain.</h1><div class="sub">Five advocates and a referee, re-planning under disruption with minimal churn.</div><div class="foot">All Qwen · deployed on Alibaba Cloud · github.com/jwlai-cloud/rehabpanel</div>'

echo "== capture frames =="
shoot "file://$BD/title.html"   "$BD/01.png"
shoot "file://$BD/problem.html" "$BD/02.png"
shoot "file://$BD/why.html"     "$BD/03.png"
shoot "$URL/#caseload"          "$BD/04.png"
shoot "$URL/#team"              "$BD/05.png"
shoot "file://$BD/how.html"     "$BD/06.png"
shoot "$URL/#rules"             "$BD/07.png"
shoot "$URL/?r=0#schedule"      "$BD/08.png"
shoot "$URL/?r=99#schedule"     "$BD/09.png"
echo "== incident: nurse sick =="; curl -sf -X POST "$URL/api/incident/sick" >/dev/null
shoot "$URL/#kpis"              "$BD/10.png"
echo "== re-plan (warm) =="; curl -sf -X POST "$URL/api/replan" >/dev/null
shoot "$URL/?r=99#schedule"     "$BD/11.png"
shoot "$URL/#kpis"              "$BD/12.png"
shoot "file://$BD/scope.html"   "$BD/14.png"
shoot "file://$BD/closing.html" "$BD/15.png"

IMGS=( "$BD/01.png" "$BD/02.png" "$BD/03.png" "$BD/04.png" "$BD/05.png" "$BD/06.png" "$BD/07.png" \
       "$BD/08.png" "$BD/09.png" "$BD/10.png" "$BD/11.png" "$BD/12.png" "$ROOT/results/gap.png" "$BD/14.png" "$BD/15.png" )
CROP=( card card card app app card app app app app app app gap card card )
NARR=(
"RehabPanel — an AI agent society that helps a rehab nurse coordinator plan the week. Built for Track 3 on Qwen Cloud."
"Here is the problem. Every cycle a rehab nurse decides which patients to follow up, when, and how, under fixed clinician time. Acuity, overdue follow-ups, continuity of care and patient preference all compete for the same scarce slots. Demand usually exceeds capacity, and the call lives in one person's head."
"Why agents? A single scheduling agent collapses the trade-off. It anchors on acuity, fills greedily, and lets overdue patients and continuity quietly rot. We wanted the conflict made explicit, and negotiated."
"Take one real week: fifty-six patients due, only forty-three slots. Each patient carries an acuity score, an overdue date, a primary nurse, and a mode preference."
"Across three nurses with fixed weekly capacity. The squeeze is real."
"So instead of one agent, we run five. Each advocate argues for exactly one objective. A charge-nurse referee resolves one conflict at a time and logs every ruling. And a pure-Python scorer, never an LLM, grades each plan, so the numbers are reproducible."
"The coordinator sets the priority rule, and it is causal: drop continuity to zero and the agents stop trading for primary-nurse matches."
"The first pass fills by acuity and scores minus one forty-one, exactly what a single agent would do."
"Then they negotiate. Advocates object, the referee rules and logs each decision. Value climbs to minus seventy, a seventy-one point gain a lone agent never finds."
"But reality breaks. A nurse calls in sick on Tuesday; her slots vanish and patients are orphaned. The live score drops to minus one hundred six."
"The coordinator hits re-plan. The society runs a warm negotiation, repairing only what the incident broke, not reshuffling the whole week."
"Just four of thirty-nine appointments change, and the score recovers. Minimal disruption: patients keep their slots. That is the efficiency that matters in a clinic."
"Across twenty-five seeded runs the society beats the single agent every time, and the advantage widens as slots get scarcer. The conflict is the point."
"To be clear: this is decision support, not autonomous scheduling. A human approves every plan, and all data is fully synthetic. No real patient records, ever."
"Five advocates, one referee, on Qwen Cloud and Alibaba Cloud. RehabPanel."
)
SUBS=(
"RehabPanel — an agent society for rehab\nscheduling · Qwen Cloud · Track 3"
"The problem: who to see, when, how —\nunder fixed time; demand > capacity"
"One agent collapses the trade-off\n(anchors on acuity, drops the rest)"
"One week: 56 patients due · 43 slots"
"3 nurses · fixed weekly capacity"
"5 advocates (1 objective each) +\nreferee + a pure-Python scorer"
"Priority rule is causal: zero continuity\n→ agents stop trading for it"
"Acuity-first draft = -141\n(= a single agent)"
"Negotiate → referee logs each ruling →\nvalue -141 → -70 (+71)"
"Nurse sick Tuesday → score drops\nto -106, patients orphaned"
"Re-plan: a warm negotiation\nrepairs only what broke"
"4 of 39 appointments change; score\nrecovers — minimal disruption"
"25 runs: society wins every time,\nwidening with scarcity"
"Decision support, not autonomous ·\nfully synthetic data"
"5 advocates + 1 referee ·\nQwen on Alibaba Cloud"
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
