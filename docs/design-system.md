# camps.ca Design System v2.0

## Colour Tokens (aligned with camps.ca)
| Token | Hex | Usage |
|---|---|---|
| Navy (primary) | `#336699` | Header, user bubbles, input border, buttons |
| Red (CTA) | `#D93600` | Links, interactive elements, focus states |
| Dark text | `#333333` | All body text |
| Secondary text | `#555555` | Metadata, muted text, blurbs |
| Canvas (background) | `#F5F5F5` | Page background |
| Surface | `#FFFFFF` | Cards, AI bubbles, input dock |
| Border | `#CCCCCC` | Dividers, input borders, filter bar |
| Amber (logo accent) | `#ffd166` | Logo `.ca` highlight |

## Tier Colours (CSC-specific)
| Tier | Hex |
|---|---|
| Gold | `#B8860B` |
| Silver | `#808080` |
| Bronze | `#8B4513` |

## Typography
- **Headers**: Nunito (wght 700–900) — loaded from Google Fonts
- **Body**: Lato (wght 400, 700) — loaded from Google Fonts
- Import: `https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Lato:wght@400;700`

## Color Zoning
Each UI zone has a distinct color treatment for intuitive recognition:
```
┌─ NAVY #336699 ── Header ──────────── [↺] ┐  Navigation chrome
├───────────────────────────────────────────┤
│  #F5F5F5 Canvas                           │
│  ┌ WHITE ──┐      ┌── NAVY ──┐           │  Chat bubbles
│  │ AI msg  │      │ User msg │           │
│  └─────────┘      └──────────┘           │
│  ┌ WHITE + tier border ──────────────┐    │
│  │ Result card                       │    │  Cards on canvas
│  │ metadata · #555555                │    │
│  │ blurb · #555555 italic            │    │
│  │ links · #D93600 red               │    │
│  └───────────────────────────────────┘    │
├─ 1px #CCC ────────────────────────────────┤
│  WHITE dock                               │  Input area
│  [Surprise Me chip]  (#D93600 text)       │
│  ┌─ 2px #336699 border input ────────┐    │
│  │  Describe what you're looking for │    │
│  └───────────────────────────────────┘    │
└───────────────────────────────────────────┘
```

## Header (Navy)
```css
.camps-topbar {
    background: #336699;
    padding: 0 1.5rem;
    height: 72px;                /* 60px on mobile ≤768px */
    position: fixed; top: 0; left: 0; width: 100%;
    z-index: 1000;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}
```
Content below header needs `margin-top: 88px` (76px on mobile).
Badge (`.camps-topbar .badge`) is hidden on mobile ≤768px.
Reset button (`.topbar-reset`) is a 36px circle, always visible.

## Topbar Reset Button
```css
.topbar-reset {
    width: 36px; height: 36px; border-radius: 50%;
    background: rgba(255,255,255,0.15);
    color: white; font-size: 1.1rem;
    border: 1px solid rgba(255,255,255,0.3);
}
```

## Surprise Me Chip
```css
.surprise-chip {
    padding: 6px 16px; border-radius: 20px;
    background: #F5F5F5; color: #D93600;
    border: 1px solid #CCCCCC;
    font-family: Nunito; font-weight: 700; font-size: 0.84rem;
}
```
Shown above chat input when no results are displayed.

## Buttons
```css
.stButton > button {
    background: #336699;
    color: white;
    border-radius: 24px;
    border: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
}
```

## Chat Input
```css
[data-testid="stChatInput"] textarea {
    border: 2px solid #336699;
    border-radius: 28px;
    background: white;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #D93600;
    box-shadow: 0 0 0 3px rgba(217,54,0,0.15);
}
```
Input dock has white background with `border-top: 1px solid #CCCCCC`.

## Chat Bubbles
```css
/* Assistant (incoming) — white surface */
background: #FFFFFF; color: #333333;
border-radius: 18px 18px 18px 4px;
box-shadow: 0 1px 6px rgba(0,0,0,0.10);

/* User (outgoing) — navy */
background: #336699; color: white;
border-radius: 18px 18px 4px 18px;
```

## Result Cards (Slim)
```
Desktop (4 lines):
Session Name · Camp Name (tier color)
Day · Ages 8-12 · Toronto · $500
Why it fits sentence (italic, no metadata repetition)
View Program ↗  ·  Camp Website ↗
```
```css
border-left: 4px solid {tier_color};
border-radius: 12px;
background: #ffffff;
box-shadow: 0 2px 8px rgba(0,0,0,0.06);
```
- Line 1: Nunito 800, `#333333` (session) + tier color (camp name)
- Line 2: Lato 400, `#555555` — dot-separated metadata
- Line 3: Lato 400 italic, `#555555` — AI blurb (never repeats metadata)
- Line 4: Nunito 600, `#D93600` — text links with ↗

## Link Attributes (SEO)
- Program page links: `rel="noopener"`, `utm_campaign=search`
- Camp website links: `rel="noopener noreferrer"`, `utm_campaign=search`
- Accordion links: `rel="noopener"`, `utm_campaign=search_more`
- No `nofollow` — editorial recommendations pass link equity

## Deep Links
Program links use: `/{prettyurl}/{camp_id}/session/{ourkids_session_id}`
Falls back to `/{prettyurl}/{camp_id}` when session ID is unavailable.
Labels: "View Program ↗" (not "camps.ca"), "Camp Website ↗".

## Mobile Breakpoints

| Breakpoint | Width | Changes |
|---|---|---|
| Tablet | ≤768px | Topbar 60px, badge hidden, min touch targets 44px, filter top offset 60px |
| Phone | ≤480px | Card padding reduced, chat bubble max-width 92% |

**Touch target rule (Apple HIG / Google Material 3):** All tappable elements minimum 44×44px.

**Font size rule:** Body text ≥ 16px (`1rem`) on mobile to prevent iOS auto-zoom on input focus.

## config.toml
```toml
[theme]
primaryColor = "#336699"
backgroundColor = "#F5F5F5"
secondaryBackgroundColor = "#ffffff"
textColor = "#333333"
font = "sans serif"
```
