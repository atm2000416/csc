# Soft Sage Design System v1.0

## Colour Tokens
| Token | Hex | Usage |
|---|---|---|
| Sage (primary) | `#8A9A5B` | buttons, accents, outgoing bubbles |
| Canvas (background) | `#F4F7F0` | page background |
| Surface | `#FFFFFF` | cards, incoming bubbles |
| Ink (text) | `#2F4F4F` | all body text |
| Glass (header) | `rgba(138,154,91,0.88)` | frosted topbar |
| Amber (logo accent) | `#ffd166` | logo `.ca` highlight |

## Typography
- **Headers**: Nunito (wght 700–900) — loaded from Google Fonts
- **Body**: Lato (wght 400, 700) — loaded from Google Fonts
- Import: `https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Lato:wght@400;700`

## Header (Frosted Glass)
```css
.camps-topbar {
    background: rgba(138,154,91,0.88);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    height: 72px;
    position: fixed; top: 0; left: 0; width: 100%;
    z-index: 1000;
    box-shadow: 0 2px 12px rgba(47,79,79,0.15);
}
```
Content below header needs `margin-top: 88px`.
Sticky filter bar: `top: 72px`.

## Topbar Action Buttons
```css
.topbar-btn {
    padding: 7px 18px;
    border-radius: 24px;
    background: rgba(255,255,255,0.18);
    color: white;
    border: 1.5px solid rgba(255,255,255,0.4);
    font-family: Nunito; font-weight: 700; font-size: 0.84rem;
}
```
Triggered via `<a href="?action=surprise" target="_self">` and `?action=reset`.

## Buttons (Claymorphism)
```css
.stButton > button {
    background: #8A9A5B;
    color: white;
    border-radius: 24px;
    border: none;
    box-shadow: 4px 4px 10px #75834d, -3px -3px 8px #9fb169,
                inset 2px 2px 6px rgba(255,255,255,0.4);
}
```

## Chat Input
```css
[data-testid="stChatInput"] textarea {
    border: 2px solid #c5d4a0;
    border-radius: 28px;
    background: white;
}
/* Remove rectangular frame from chat input container */
section[data-testid="stBottom"],
section[data-testid="stBottom"] > div,
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div {
    background: transparent; border: none; box-shadow: none;
}
```

## Chat Bubbles
```css
/* Assistant (incoming) — white surface */
background: #FFFFFF; color: #2F4F4F;
border-radius: 18px 18px 18px 4px;
box-shadow: 0 1px 6px rgba(47,79,79,0.10);

/* User (outgoing) — sage green */
background: #8A9A5B; color: white;
border-radius: 18px 18px 4px 18px;
```

## Result Cards
```css
border-left: 4px solid {tier_color};
border-radius: 12px;
background: #ffffff;
box-shadow: 0 2px 8px rgba(47,79,79,0.08);
```
- Program name: Nunito 800, `#2F4F4F`
- Camp name: Nunito 600, tier colour
- Blurb: Lato italic, `#4a6060`
- Buttons: `background: #8A9A5B`, `border-radius: 24px`

## Tier Colours
| Tier | Hex |
|---|---|
| Gold | `#B8860B` |
| Silver | `#808080` |
| Bronze | `#8B4513` |

## config.toml
```toml
[theme]
primaryColor = "#8A9A5B"
backgroundColor = "#F4F7F0"
secondaryBackgroundColor = "#ffffff"
textColor = "#2F4F4F"
font = "sans serif"
```
