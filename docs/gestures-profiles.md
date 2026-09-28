# Profile gestures (iteration 2 — exploratory)

## What data Frametop already has

- HMD pose (position + full orientation) every frame in `ft-screens`
- Left/right controller poses and tip lasers
- Existing wrist-aim rings while dragging a screen
- Existing visibility “gesture” mode: look toward a chosen controller within an angle
- Input-relay button/key actions (including new profile slot / next / previous)

OpenVR on the Frame path does **not** expose eye-tracking gaze in the code Frametop uses today. Attention fade therefore uses **head forward** (HMD −Z), not pupils.

## Why free-air gestures were not shipped

Reliable next/previous profile or show/hide HUD from bare hand waving needs either:

1. a deliberate held pose with clear enter/exit hysteresis, or
2. a button/chord the user already intends,

otherwise false positives interrupt work. Controller orientation-only “flick” recognition is noisy on the Frame’s tracking and conflicts with normal pointing.

## Practical options (later)

| Idea | Data | Risk | Notes |
|------|------|------|-------|
| Look-at-wrist + mapped button | Existing gesture angle + input action | Low | Reuse visibility gesture; bind `profile_next` on a spare button while looking at wrist |
| Hold controller tip up for N ms | Controller orientation | Medium | Needs hold time ≥400 ms and a deadzone |
| Chrome slot buttons / input actions | Already implemented | Lowest | Preferred for iteration 2 |

## Recommendation

Keep profile switching on **VR chrome slot buttons** and **Input Settings actions** (`profile_slot_N` / `profile_next` / `profile_previous`), which all resolve through `ft-layout action` (canonical names `profile.slot.N`, …). Revisit a look-at-wrist + button chord only after those feel solid on the headset.
