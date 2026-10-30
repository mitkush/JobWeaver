# Website visual polish

The existing page accents and corner brackets remain the basis of the website identity.
The navbar and favicon use a woven-path mark. Full-page and inline loading indicators
use the same mark, with an orbit that stops under Reduce Motion.

- Page labels stay visible. A short border highlight runs once on entry and once on hover.
- Feed loading shows four decorative skeleton cards with one accessible loading status.
- Draft generation retains the server's progress text and adds the branded loading mark.
- Buttons have a small press response; selected icon buttons and success messages have
  a brief scale response. Dialogs and toast messages enter over 180 ms.
- Reduce Motion disables animations and transitions, hides the decorative border pass,
  and keeps loading labels, static placeholders and the ordinary border visible.
- No animation delays data display or adds a fabricated progress percentage.

Validation: 145 frontend tests pass, plus lint, typecheck and production build.
A local Brave walkthrough used mocked API responses against the production build:
light and dark Feed, loading skeletons, 375px layout without horizontal overflow,
valid border dimensions and hover replay, zero running animations under Reduce Motion,
and no page JavaScript errors. No production data or services were used.
