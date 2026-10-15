# Lato26 Slack-style specimen

A static, responsive Slack-inspired interface using the repository's Lato26 variable upright and italic fonts (weight axis 100–900). The conversation uses the user-supplied A Few Good Men excerpt, with full character names and consecutive messages from the same speaker grouped as paragraphs under one avatar. Character avatars use the three user-supplied portraits, cropped to their rounded frames with CSS. This is an independent type specimen, not a Slack product.

Published at https://muglug.github.io/lato-source/slack/ through GitHub Pages using `.github/workflows/publish-pages.yml` (every push to `master`, or a manual workflow run).

Preview from the repository root:

```sh
python3 -m http.server 8765 --directory docs
```

Open http://localhost:8765/slack/. No build, JavaScript, or external assets are required. Font license is included in assets/LICENSE.txt. The workflow copies both committed variable fonts from `build/Lato26-Variable/`, adds content-based cache keys to the font and stylesheet URLs, and deploys `docs/`. It does not rebuild fonts from source or commit generated copies back to Git. Push updated TTF builds to publish new fonts.

For the same refresh locally, run `python3 .github/scripts/refresh_specimen_fonts.py` from the repository root. The helper uses only the Python standard library.

Typography is matched against the supplied 2354×1916 Retina reference at a 1177×958 CSS viewport: 15px body/sidebar, 18px headings, and 12px timestamps. The main conversation scrolls independently inside the fixed frame; there is no thread pane. Names and the channel title use weight 800. The supplied speech includes selective bold and italic emphasis.

The aubergine palette is sampled from the original reference screenshot after conversion from its embedded display profile to sRGB. The sidebar background SVG interpolates sampled left/right vertical gradients; the rail and top bar use sampled CSS gradients. Selected channel: #f9edff; active rail item: #744a77; search field: #744777 to #6f4373.
