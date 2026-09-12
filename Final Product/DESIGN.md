---
name: Playful Wonder
colors:
  surface: '#faf8ff'
  surface-dim: '#d5d9ef'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e3e7fe'
  surface-container-highest: '#dde1f8'
  on-surface: '#161b2b'
  on-surface-variant: '#3e4850'
  inverse-surface: '#2b3041'
  inverse-on-surface: '#eef0ff'
  outline: '#6e7881'
  outline-variant: '#bdc8d2'
  surface-tint: '#006590'
  primary: '#006590'
  on-primary: '#ffffff'
  primary-container: '#2bb8ff'
  on-primary-container: '#004665'
  inverse-primary: '#88ceff'
  secondary: '#7c5800'
  on-secondary: '#ffffff'
  secondary-container: '#feb700'
  on-secondary-container: '#6b4b00'
  tertiary: '#b41963'
  on-tertiary: '#ffffff'
  tertiary-container: '#ff88b1'
  on-tertiary-container: '#840045'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#c8e6ff'
  primary-fixed-dim: '#88ceff'
  on-primary-fixed: '#001e2e'
  on-primary-fixed-variant: '#004c6e'
  secondary-fixed: '#ffdea8'
  secondary-fixed-dim: '#ffba20'
  on-secondary-fixed: '#271900'
  on-secondary-fixed-variant: '#5e4200'
  tertiary-fixed: '#ffd9e2'
  tertiary-fixed-dim: '#ffb1c8'
  on-tertiary-fixed: '#3e001d'
  on-tertiary-fixed-variant: '#8e004b'
  background: '#faf8ff'
  on-background: '#161b2b'
  surface-variant: '#dde1f8'
  mint-fresh: '#1DD3B0'
  playful-purple: '#8C52FF'
  candy-pink: '#FF599C'
  sunny-yellow: '#FFB800'
  sky-blue: '#2BB8FF'
  bubblegum-light: '#FFF0F6'
  mint-light: '#E8FAF6'
  sky-light: '#EBF8FF'
  canvas-cream: '#FFFDF9'
  surface-card: '#FFFFFF'
  border-soft: '#F0EEED'
typography:
  headline-xl:
    fontFamily: Rubik
    fontSize: 44px
    fontWeight: '800'
    lineHeight: 52px
  headline-xl-mobile:
    fontFamily: Rubik
    fontSize: 32px
    fontWeight: '800'
    lineHeight: 40px
  headline-lg:
    fontFamily: Rubik
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
  headline-lg-mobile:
    fontFamily: Rubik
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 34px
  headline-md:
    fontFamily: Rubik
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-sm:
    fontFamily: Rubik
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-lg:
    fontFamily: Rubik
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
  label-md:
    fontFamily: Rubik
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 18px
  label-sm:
    fontFamily: Rubik
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1.25rem
  space-xs: 0.375rem
  space-sm: 0.75rem
  space-md: 1.25rem
  space-lg: 2rem
  space-xl: 3rem
---

## Brand & Style
This design system crafts an optimistic, joyous, and approachable world tailored for educational platforms, creative tools, family services, and gamified digital experiences. It merges exuberant playfulness with purposeful structure—ensuring that vibrant aesthetics never compromise usability, accessibility, or informative clarity.

The visual style blends **tactile softness**, **bold pop-geometry**, and **clean modern clarity**. Surfaces feel chunky, inviting, and buoyant, anchored by rounded forms, buoyant micro-interactions, and high-legibility typographic hierarchies. Whitespace acts as a vital canvas, allowing vibrant multi-colored accents to shine without sensory overload.

## Colors
The color architecture celebrates vibrant chromatic contrast while preserving a clean, crisp background framework to guarantee high readability:

- **Primary (`sky-blue`, `#2BB8FF`)**: The cheerful guide color used for core interactive elements, key actionable links, and primary progress indicators.
- **Secondary (`sunny-yellow`, `#FFB800`)**: The warm motivator, utilized for calls-to-action, high-achievement celebrations, star indicators, and alerts.
- **Tertiary (`candy-pink`, `#FF599C`)**: The spark of delight, driving favorites, critical notifications, and highlight badges.
- **Accent Mints & Purples**:
  - `mint-fresh` (`#1DD3B0`): Validation, positive stats, completed stages, and supportive health cues.
  - `playful-purple` (`#8C52FF`): Deep creative highlights, category demarcation, and discovery prompts.
- **Neutral (`#313647`)**: Deep blueberry charcoal replacing harsh black, ensuring comfortable reading contrast with an approachable tone.
- **Surfaces**: Pure whites and creamy soft tones (`#FFFDF9`) frame colorful cards, preventing visual fatigue.

## Typography
Typographic rhythm balances soft, rounded geometry with uncompromised clarity:

- **Headlines & Labels (`Rubik`)**: Features rounded letterforms and organic terminals that communicate friendliness and joy. High weights (700 and 800) give titles a punchy, poster-like character.
- **Body Copy (`Plus Jakarta Sans`)**: Delivers broad counters and clear aperture shaping for effortless scanning across long passages, instructions, and data sets.
- **Numbers & Data Counters**: Use tabular or medium weights of `Rubik` to transform stats and scores into bold, gamified focal points.

## Layout & Spacing
The layout follows a fluid 12-column grid on desktop (conforming to a maximum container of `1240px`) and transitions gracefully through an 8-column layout on tablets down to a single-column stack on mobile viewports.

Generous vertical and horizontal breathing room prevents vibrant colors from competing with each other. Key structural rules:
- **Component Padding**: Containers, panels, and modal cards utilize roomy padding (`space-lg`) to preserve a plush, airy tactile presence.
- **Stacking Spacing**: Content blocks are separated by `space-xl` to maintain clean visual segments.
- **Touch Targets**: All touch components adhere to a minimum size of 48px to accommodate small fingers, stylus inputs, and quick interactions.

## Elevation & Depth
Depth in this design system avoids gloomy, realistic drop shadows in favor of **chunky, bouncy, physical dimensionality**:

- **Pop Shadow (Tactile Lift)**: Primary interactive elements use crisp, low-blur offset drop shadows tinted with deep violet/navy (`box-shadow: 0 4px 0px rgba(49, 54, 71, 0.12), 0 8px 24px rgba(49, 54, 71, 0.06)`).
- **Pressed States**: Active interactive states collapse their offset shadow to `0 1px 0px`, physically dropping the button downward by 2–3px to evoke a bouncy toy button press.
- **Colored Ambient Auras**: High-priority cards (such as quest completions or active badges) cast soft, diffused glows keyed to their primary hue (e.g. `rgba(43, 184, 255, 0.25)`).
- **Layering**: Modals and floating sheets sit above a translucent milky backdrop with a slight blur (`backdrop-filter: blur(8px)` with `rgba(255, 255, 255, 0.8)`).

## Shapes
Forms are inherently bubbly, friendly, and soft. The system standardizes on **Pill-shaped (Scale 3)** roundedness:

- **Micro Elements (Pills & Badges)**: Full pill radius (`rounded-full` / `9999px`) for tags, chips, and small triggers.
- **Standard Controls (Inputs & Buttons)**: Highly rounded curvatures (`1.25rem` to `1.5rem`) that ensure no sharp corners exist to disrupt the friendly mood.
- **Cards & Modal Sheets**: Rounded corners of `1.5rem` (`24px`) to `2rem` (`32px`), yielding warm, cushion-like presentation surfaces.
- **Borders**: Chunky 2px to 3px solid borders in low-saturation neutral tints or self-colored pastel shades reinforce the hand-crafted, illustrated visual style.

## Components

### Buttons
- **Primary Buttons**: Saturated `sky-blue` or `candy-pink` base with white `Rubik` bold typography. Height 52px, pill-rounded, equipped with a 3px dark-offset bottom edge creating an authentic 3D "push-down" button feel.
- **Secondary Buttons**: White background with a 2.5px solid border colored in the active hue, transitioning to a light pastel wash upon hover.
- **Icon Action Buttons**: Circular pill buttons with bold, dual-tone friendly icons.

### Chips & Badges
- **Pill Badges**: Complete circular caps (`rounded-full`), employing 50% pastel background fills with high-saturation foreground text (e.g., `mint-light` background paired with a deep mint label).
- **Status Indicators**: Playful emoji or circular bubbly dot icons nestled inside pill tags.

### Cards & Panels
- **Informative Content Cards**: Pure white surfaces bound by soft outer borders or subtle pastel headers. Cards maintain an internal padding of `space-md` to `space-lg` with rounded-2xl (`24px`) corners.
- **Categorical Accent Tops**: Cards can feature a 6px curved top rim painted with `sunny-yellow`, `candy-pink`, or `mint-fresh` to indicate categories at a glance.

### Inputs & Form Controls
- **Input Fields**: Tall (48px–52px) rounded containers with a smooth off-white fill (`#FFFDF9`), framed by a 2px stroke in `#E8E6E4`. Focus states morph the stroke into vibrant `sky-blue` with a soft outer ring.
- **Checkboxes & Radios**: Extra-large (24px x 24px) rounded squares and circles featuring animated bouncy check marks and pop feedback when toggled.

### Lists & Navigation
- **Progress Trackers**: Thick rounded progress bars (16px height) with candy-striped or solid gradient fills and pill milestone badges.
- **List Items**: Floating island cards stacked vertically with generous `space-sm` gaps, each providing distinct hover scale reactions (`scale: 1.02`).