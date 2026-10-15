# Lato26 Slack-style specimen

A static, responsive Slack-inspired interface using the repository's Lato26 variable upright and italic fonts (weight axis 100–900). The conversation uses the user-supplied A Few Good Men excerpt, with full character names and consecutive messages from the same speaker grouped as paragraphs under one avatar. Avatars are flat colored rectangles. This is an independent type specimen, not a Slack product.

Published at https://muglug.github.io/lato-source/slack/ through GitHub Pages (master branch, /docs directory).

Preview from the repository root:

```sh
python3 -m http.server 8765 --directory docs
```

Open http://localhost:8765/slack/. No build, JavaScript, or external assets are required. Font license is included in assets/LICENSE.txt. To refresh fonts, copy build/Lato26-Variable/Lato26-Variable.ttf and Lato26-VariableItalic.ttf to assets/lato26.ttf and assets/lato26-italic.ttf respectively.

Typography is matched against the supplied 2354×1916 Retina reference at a 1177×958 CSS viewport: 15px body/sidebar, 18px headings, and 12px timestamps. The single conversation pane deliberately clips overflow and does not scroll; there is no thread pane.
