> Style research from Scroll Studio by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. Licensed under the GNU AGPL-3.0 with additional terms (NOTICE.md): credit it with this notice, unchanged, wherever it is used, and don't present it as your own work.

# Scroll Studio style research: styles 24 and 25

**Zoetrope, Flipbook**

Prepared 2026-10-12 for the Scroll Studio engine, as part of the animation-technique batch (styles 22 to 27). These two styles come from the two oldest ways of making drawings move by hand: a drum you spin and a pad you thumb. Both are pre-cinema toys, and both answer the batch's question in a different way: *what does scrolling become inside this technique?* In the zoetrope, scrolling is **force**: it spins a flywheel, and the animation only exists above a certain speed. In the flipbook, scrolling is **the thumb**: every notch lets go of one page, and the drawing is wherever your thumb has got to.

> **How to read the citations.** URLs are inline. Where a claim comes from general animation or design knowledge and not from a source I retrieved, I say "(general knowledge)". Some figures (frame counts, installation sizes) differ between sources; where they do I say so instead of picking one silently.

---

## Cross-cutting principle: two pre-cinema scroll models

| Style | What scroll *is* | Time quantisation | Motion curve | Spatial axis | Primary renderer |
|---|---|---|---|---|---|
| Zoetrope | **Torque on a flywheel.** Scroll speed (and a sideways drag) spins a slotted drum; scroll *position* only decides which strip is loaded | A closed loop of 12 frames. Below the fusion speed you see the drum turn continuously and the frames slide past one by one; above it the slits strobe and the frames lock in place and animate | Physics, not tweens: impulse in, exponential friction out (a spin-down lasts seconds). Strip swaps are lifts on a scrubbed scroll window | Rotation about a vertical axis: a cylinder seen from just above its rim; the camera drops to slit height as the drum speeds up | One WebGL canvas (three.js drum, strips drawn into canvas textures) plus DOM caption card |
| Flipbook | **The thumb on a pad.** One wheel notch (about 100 px) releases one page; scroll position is the page number, forwards and backwards | Discrete pages. Each page is one drawing; a slow scroll bends the next page's corner, the notch lets it go | A released page peels over in about a quarter of a second (fast start, settling as it lies over). A fast scroll riffles several pages in flight at once | Depth: a pad of paper seen from above, hinged at a peg bar along its top edge; pages peel up from the lower corner and fold over the top | Canvas 2D (a fold-and-reflect page peel, pencil drawings with line boil) plus real DOM text on the resting page |

Neither model is used by any of the 21 existing styles. Kinetic type and liquid morph react to scroll *velocity* too, but as a deformation of the content (skew, wobble); in the zoetrope velocity is the only thing that makes the picture *exist as motion*, and position plays no part in the animation. Pixel art steps frames, but its frames are a sprite walking through a level; the flipbook's frames are the pages of the site itself, and you move through them like paper.

---

## 24. Zoetrope

### 24.1 Origin and defining aesthetic

William George Horner described the device in 1833 or 1834 as the *daedaleum*; he published it but never patented it ([Museum of the History of Science, Oxford](https://www.mhs.ox.ac.uk/exhibits/fancy-names-and-fun-toys/zoetrope/); [Wikipedia: Zoetrope](https://en.wikipedia.org/wiki/Zoetrope)). The toy as people know it is William E. Lincoln's: he applied for a US patent on 27 July 1866 as assignor to Milton Bradley, granted 23 April 1867 (Wikipedia, above; Oxford gives a conflicting later date). Lincoln's version put **the slits on a band above the pictures**, which is what made the picture strips easy to swap, and Milton Bradley sold the strips in numbered series of twelve (Wikipedia, above). James Clerk Maxwell fitted concave lenses to the slits in 1868 to remove the distortion (Oxford, above), and made strips of physics subjects such as vortex rings (Wikipedia). British makers sold it as "The Wheel of Life"; the Science Museum holds strips such as a horse and rider jumping a fence and two acrobats back-flipping ([Science Museum Group: Wheel of Life No. 30](https://collection.sciencemuseum.org.uk/objects/co8593655/zoetrope-strip); [Wheel of Life strip](https://collection.sciencemuseumgroup.org.uk/objects/co8593656/zoetrope-strip-the-wheel-of-life)).

Émile Reynaud's **praxinoscope** (1877) replaced the slits with a ring of twelve mirrors at the centre, one per picture, which gave a brighter, steadier image ([Wikipedia: Praxinoscope](https://en.wikipedia.org/wiki/Praxinoscope)). The zoetrope never died: Toshio Iwai supervised the Ghibli Museum's 3D Totoro zoetrope (2001), figures on a turntable that come alive under a strobe ([Boing Boing visit](https://boingboing.net/2010/07/26/a-visit-to-spirited.html); Wikipedia), and Pixar's *Toy Story* zoetrope, built with Gregory Barsamian and Toshio Iwai, mounts posed maquettes on a turntable lit by a strobe ([Academy Museum](https://www.academymuseum.org/en/content/article/toy-story-3d-zoetrope); sources disagree on the number of figures). John Edmark's 3D-printed "blooming" sculptures are shot at a shutter or strobe synchronised to one flash per 137.5° of rotation, the golden angle, so the petals appear to flow ([Motionographer](https://motionographer.com/2015/01/16/fibonacci-zoetrope-sculptures/); [Dezeen](https://www.dezeen.com/?p=631400)). Eric Dyer films spinning "cinetropes" with a fast-shutter camera, which does the slits' job ([UMBC IRC: Bellows](https://irc.umbc.edu/bellows-zoetropic-filmmaking/)).

The most important reference for a *scroll* site is the **linear zoetrope**. Bill Brand's *Masstransiscope* (1980) puts 228 hand-painted panels behind a row of slits in the disused Myrtle Avenue subway station; the passing train is what "spins" it, and riders see about twenty seconds of animation ([nycsubway.org](https://www.nycsubway.org/wiki/Artwork:_Masstransiscope_(Bill_Brand)); [Creative Time](https://creativetime.org/projects/masstransiscope/)). Joshua Spodek's tunnel advertisements (Atlanta, 2001, then Washington, BART and New York) work the same way (Wikipedia). In both, **the viewer's own motion makes the picture**, and a train that is too slow sees only slivers. That is exactly the relation between a visitor's scroll speed and the drum in this style.

**Visual signatures:**
1. **The drum.** A black or lacquered cylinder on a turned stand, a band of narrow vertical slits round its upper half, the picture strip glimpsed inside through them.
2. **The strip.** A long paper band of 12 (sometimes 13) frames separated by rules, printed in chromolithograph colours on cream: black silhouettes, vermilion, Prussian blue, ochre. A printed title and series number along the edge ("No. 3").
3. **Cyclic subjects.** A juggler, a horse, a bird beating its wings, a ball bouncing, an acrobat. Every subject is a **loop**: the last frame leads back to the first.
4. **The box of strips.** The toy came with a box of interchangeable strips; part of the ritual is choosing the next one, dropping it into the drum and giving it a spin.
5. **Flicker and darkness.** Through the slits the picture is dim and slightly flickering; the eye fills it in (general knowledge).

**How the illusion works, and why it matters for the mechanic.** Each slit gives the eye a brief look at the frame opposite, then blocks the view until the next slit arrives with the next frame in the same place, so the frames do not smear (Wikipedia, above). With as many slits as frames, the subject animates on the spot; draw one frame more or fewer than there are slits and the figures appear to travel round the drum (general knowledge). Below a certain rate the pictures read as separate snapshots; the brain links them into motion (the beta effect, not retinal "persistence") once they arrive fast enough. Early film ran between 12 and 24 frames a second ([UAL research paper on persistence of vision and apparent motion](https://ualresearchonline.arts.ac.uk/id/eprint/21202/2/f4fb8655-0e0a-461f-8852-163a38bd629c.pdf)); hand-made flip animation is commonly said to look smooth from about 12 to 15 ([RAFT activity guide](https://raft.net/wp-content/uploads/2020/08/280-Animated-Flip-Books.pdf)). So the style sets its fusion point at about 10 frames per second through the slits: under it, frames; over it, motion.

### 24.2 Layout and information architecture

- **One instrument, not a stack of panels.** The screen is a parlour table under a lamp. A large drum stands right of centre (desktop) or across the top half (phone). It is the only picture on the page, and it never scrolls away.
- **Every section is a strip.** Each block becomes a 12-frame strip drawn from its own content (the hero's headline word, the product's phone, the stats, a walking figure for the timeline). Moving to the next section means **lifting the strip out of the drum and dropping in the next one**. Lists with real weight (features) are one strip per item, so each feature gets its own swap.
- **The caption card.** Left of the drum (below it on a phone) sits the printed card for the strip that is loaded: series number ("Strip No. 4 of 12"), title, body, buttons. It is real HTML, always fully readable at rest.
- **The box of strips (nav).** A column of strip labels, each a numbered paper tab, stands at the right edge; the loaded strip's tab is pulled out. Clicking one scrolls to it. On phones it collapses into the header.
- **The tachometer.** A small brass dial reads the drum's rate in frames per second, with two zones printed on its face, *frames* and *motion*. It teaches the mechanic without a word of instruction, and carries the "give it a spin" button.

### 24.3 Signature interactions and scroll behaviour

**How scroll feels:** like pushing a heavy wheel. Scroll speed is turned into torque on a flywheel; the drum keeps turning after you stop and winds down over several seconds. Scroll up and it spins backwards, so the loop plays in reverse. Position matters only at the boundaries between strips.

**What scroll drives:**
- **Spin.** Angular speed comes from scroll velocity (impulse plus friction, capped). The rate in frames per second (slits passing per second) drives everything else.
- **Three regimes.** *Stopped:* the camera rises and looks over the rim, so you see the inside of the strip as printed, frames side by side. *Slow* (under about 8 frames a second): the drum turns, the slats sweep past and the frames slide by as separate pictures. *Fast* (over about 10): the slits strobe; the frames lock into place and the loop comes alive, while the slatted wall blurs to a grey veil and the camera drops to slit height. The lock-in moment is the signature beat.
- **Strip swap (section transition).** At each boundary a short scrubbed window lifts the old strip straight up out of the open drum, a curling paper ring rising off the top, and lowers the next one in. It is tied to scroll position, so it reverses if you scroll back. When a strip lands, the drum gets a push, as a hand would give it, so each section opens with its loop alive and then winds down through separate frames to a halt. That rhythm (alive, frames, still) repeats for every section.
- **Travel strips.** For lists that are a procession (stats), the strip is drawn as a *parade*: the figures advance a little each time a slit passes, like a 13-frame strip in a 12-slit drum, so at speed the numbers march round the drum past the viewing slits.

**Headline arrival:** through the slits. A new caption's heading is first seen through a moving vertical slit mask that sweeps with the drum; as the strip settles the slits widen until the text is solid. The headline is never typed, faded or slid; it *fuses*, the way the picture does.

**Stats:** a parade. The figures are printed as cartouches on one travelling strip and march round the drum when it spins; the caption card prints them as a playbill of large numerals.

**Feature list:** one strip per feature. The feature's title becomes the strip's subject (its letters hop in a wave round the drum), its tag is the strip number. The caption card lists all features and pulls the loaded one forward.

**Section transitions:** strip out, strip in, push. No fades, no cuts, no sideways slides.

**Pointer:** grab the drum and spin it. A horizontal drag on the drum turns it directly; letting go flings it with the drag speed. Vertical swipes still scroll (the drum uses `touch-action: pan-y`). The tachometer's button gives the same push from the keyboard.

**CTA:** the last strip carries the call to action as its subject, its letters bouncing round the drum, and the caption card holds the button. The tachometer reads "motion" as you arrive: the page ends with the wheel alive.

**Real-world references:** *Masstransiscope* (above) for the moving-viewer principle; the Ghibli and Pixar strobe zoetropes for the moment of lock-in; Milton Bradley and *Wheel of Life* strips for the printed look; Edmark for how a strobe rate can make one object perform.

### 24.4 Component treatments

| Component | Treatment |
|---|---|
| Nav | The box of strips: numbered paper tabs at the right edge, the loaded one pulled out. A slim lid band at the top with the wordmark in wood-type capitals and the nav CTA. |
| Buttons | Printed tickets: cream card, double rule border, small caps. Primary is vermilion with cream text. Hover lifts the ticket a few pixels. |
| Hero | Strip No. 1. Subject: the theme artwork's frames if the site has `theme.art`, otherwise the headline's accent word leaping in a squash-and-stretch arc. Caption carries the `<h1>`. |
| Intro | A bird in flight (Marey's gull, flapping on the spot). Caption: kicker, title, body. |
| Features | One strip per feature: the title's letters in a travelling wave, the tag numeral printed in the corner of each frame. |
| Product | A phone turning on a turntable, 12 views round 360°, its screen drawn from the device data. Caption: kicker, title, body, tags as printed labels. |
| Stats | One parade strip: each stat a cartouche (value, unit). Caption: a playbill of large Didone numerals with small-caps labels. |
| Timeline | A walking figure with milestone posts (each `when`) sliding past behind it. Caption: steps listed as numbered stations, the current one marked by scroll position. |
| Quote | A speaking profile in a cameo frame, a speech balloon swelling and shrinking. Caption: the quote set large in italic with a printer's manicule before the attribution. |
| FAQ | A question mark tumbling end over end. Caption: native `<details>` list styled as a Q and A leaflet. |
| CTA | The button label's letters hopping round the drum over a turning sunburst. Caption: kicker, title, the ticket button. |
| Gallery, strip, orbit, unknown | A bouncing ball strip (the first exercise of every animator); default markup in the caption, restyled. |
| Film and other scenes | Intermissions: the scene slides up over the parlour and plays full width; the drum is waiting underneath when it has passed. Unknown block types are treated the same way. |

### 24.5 Typography and colour

- **Display:** **Bodoni Moda** (variable, optical sizes 6 to 96, weights 400 to 900): the high-contrast Didone of 1860s and 70s posters and toy-box lids.
- **Labels:** **Alfa Slab One**, a heavy slab in the spirit of the wood types on playbills, used for strip numbers and the tachometer.
- **Body:** **Libre Caslon Text**, a book face of the period, comfortable at body sizes.
- **Mono:** **Cutive Mono** for frame numbers and small readouts.
- **Palette:** a dark parlour (walnut black `#14100d`) lit by a warm lamp; cream text `#efe3c8`; strip paper `#efe2c4`; vermilion `#d4482c` as the accent (buttons, strip numerals); brass `#c9a24a` for rules and the dial; Prussian blue `#24476b` and ochre `#c78f2a` in the printed strips only.

### 24.6 Implementation

- **Stage:** a fixed full-screen WebGL canvas (three.js, lazy chunk). The drum is a slatted outer wall (an alpha-cut cylinder, front side lacquer, back side dark), an inner strip ring (canvas texture of 12 frames, seen through the slits and over the rim), a printed base disc, a turned stand. One warm key light and ambient.
- **Strobe model:** keep two angles, the drum's true angle θ and the strip's displayed angle. Below the fusion rate they are equal (frames slide past). Above it the strip is drawn at θ rounded to the nearest slit pitch while the outer wall keeps turning and fades to a veil: what the eye integrates through a strobing slit is precisely the strip at those aligned instants. Hysteresis (lock at 10 fps, release at 8) avoids chatter.
- **Flywheel:** `ω += gain · scrollVelocity`, `ω *= exp(-friction · dt)`, capped; dragging the drum sets θ directly and releases with the drag speed.
- **Strips:** drawn once per section into a 2D canvas (12 frames plus the printed margins), uploaded as textures; at most two are alive (the leaving and the arriving strip).
- **Sections:** each block becomes a spacer whose height is its share of the scroll; its caption is fixed in the card area and shown while its section holds the middle of the screen. Strip swaps are scrubbed over a window around each boundary.
- **Performance:** pixel ratio capped (1.5 on phones), the render loop sleeps when the drum is still and nothing is swapping, and while a scene section covers the screen.

### 24.7 Anti-patterns

- **A spinning carousel of cards.** A 3D ring of feature cards that rotates as you scroll is a coverflow, not a zoetrope. The zoetrope's picture comes *from the spin* and is seen *through slits*.
- **Velocity as decoration.** If the page looks the same at every scroll speed, the mechanic is lost. Speed must change what you see: separate frames below the threshold, a living loop above it.
- **Real flashing.** Do not simulate the strobe by flashing the screen. The lock-in is shown by holding the frames still while the drum turns; luminance stays steady (WCAG 2.3.1).
- **Same-as-Kinetic-type trap:** both react to speed. Kinetic type *distorts the type* with velocity; here velocity *animates a separate picture*, and the type never moves except through the slit mask on arrival.
- **Same-as-Liquid-morph trap:** liquid morph stretches its world when flung and settles with surface tension. The zoetrope has rigid parts only: a wheel, a strip, slits.
- **Same-as-Retro-VHS trap:** VHS turns speed into fast-forward noise on a tape. The zoetrope has no timeline to search: the loop is closed, and speed decides only whether it lives.

### 24.8 Reduced-motion fallback

The drum is not shown. Each section prints its strip **laid flat** beside its caption, in a normal reading flow: the 12 frames with their numbers and the printed title, cut in two and laid one half above the other so the drawings read at a useful size, like a strip lifted out of the box. Nothing turns, no slit masks. The technique stays recognisable as an object: a printed zoetrope strip is the zoetrope at rest.

### 24.9 UX signature

**Your scroll is the hand on the wheel.** One lacquered drum stands under a lamp and every section is a paper strip dropped into it. Scroll gently and the drum turns, and you see the drawings slide past the slits one by one. Scroll hard and the slits start to strobe: the frames lock in place and the loop comes alive (a word leaping, a phone turning, a figure walking past the milestones), while the dial swings from *frames* into *motion*. Stop and it winds down, and the camera lifts to look over the rim at the strip itself. Between sections the strip is lifted out and the next dropped in with a push. The feeling is *the illusion explained by your own hand*: the visitor discovers that the picture only exists while they keep the wheel going.

---

## 25. Flipbook

### 25.1 Origin and defining aesthetic

The flipbook is the first animation with a **linear** sequence of pictures instead of a circular one. John Barnes Linnett patented it as the *kineograph* on 18 March 1868 ([Wikipedia: Flip book](https://en.wikipedia.org/wiki/Flip_book); [Wikipedia: John Barnes Linnett](https://en.wikipedia.org/wiki/John_Barnes_Linnett)); Pierre-Hubert Desvignes is credited with a similar "folioscope" around 1860 ([Museum of the History of Science, Oxford: Kinora](https://www.mhs.ox.ac.uk/exhibits/fancy-names-and-fun-toys/kinora/)). Max Skladanowsky showed his serial photographs as a flipbook in 1894, a year before his projector; Herman Casler's Mutoscope (1894) mechanised it with the pages on a crank-turned drum, a fixture of penny arcades; Henry William Short's Filoscope (1897) held the book in a metal case with a lever (Wikipedia; Oxford, above). The German name says how it is used: *Daumenkino*, "thumb cinema" (Wikipedia).

It is also the animator's own medium. Animators "flip" and "roll" their drawings between their fingers to check timing before anything is shot, and the drawings sit on punched animation paper held by a peg bar so every page registers with the next (general knowledge; [Scout Life: how to make a flipbook](https://scoutlife.org/hobbies-projects/projects/156969/how-to-make-an-animated-flipbook/) on peg bars, binder clips and light boxes). The Walt Disney Family Museum's guide asks for at least 20 pages glued along a binding edge ([WDFM: How to Make a Flipbook](https://www.waltdisney.org/sites/default/files/2020-04/WDFM_HowToMakeaFlipbookFinal2.pdf)); guides commonly suggest 30 to 60 pages for one to two seconds, and about 12 drawings a second (or 24 pages "on twos") for smooth motion ([RAFT activity guide](https://raft.net/wp-content/uploads/2020/08/280-Animated-Flip-Books.pdf)). Living makers: Volker Gerling walks across Germany making photographic flipbook portraits (36 shots in 12 seconds) and performs them under a camera as *Portraits in Motion*, a Total Theatre Award winner at the 2015 Edinburgh Fringe ([Total Theatre](https://totaltheatre.org.uk/volker-gerling-portraits-in-motion/); [CBC](https://amp.cbc.ca/lite/story/1.3944209)); Andy Murphy (Andymation) makes long pencil flipbooks and kits ([The Kid Should See This](https://thekidshouldseethis.com/post/how-to-make-a-flipbook-andymation)). Walt Disney Animation Studios has opened its films since 2007 with a logo that evokes a flipbook (Wikipedia, above).

**Visual signatures:**
1. **Paper and pencil.** Off-white bond paper, graphite line, the animator's blue rough pencil and red key pencil, smudges, erased construction lines.
2. **Line boil.** Every page is redrawn by hand, so even a held drawing shimmers slightly from page to page (general knowledge).
3. **The stack.** Page edges visible in thin lines along the bottom and side, thinning as you go; page numbers in the corner; a clip or peg bar holding it.
4. **The bend.** A page bent under the thumb before it is let go, then the slap as it lands.
5. **Classic exercises.** The bouncing ball, the paper plane, the walk cycle, a shape morphing into another, hand-lettering that writes itself (general knowledge).

### 25.2 Layout and information architecture

- **The site is one pad.** A single pad of animation paper lies on a dark desk, centred, held at the top by a peg bar. It never scrolls away; the *pages* go. The pad is landscape on desktop and portrait on phones.
- **Each section is a run of pages.** A section owns a run of 10 to 40 pages, sized from its content. On those pages its drawing animates and its text is written in. Item lists are runs within the run (features, stats, steps, questions).
- **The page layout.** Desktop: text column on the left of the page (kicker as a pencil label, handwritten headline, body), animation field on the right inside a faint field-guide rectangle. Phone: field on top, text below. Every page carries its number in the corner and the scene and frame count in animator's notation ("SC 03 · 07/18").
- **Index tabs (nav).** Section names stick out of the pad's right edge as paper tabs at their depth in the stack; tabs of sections already flipped are gone. Clicking one thumbs straight to it. On phones the header carries the page counter and a menu.
- **The desk.** Furniture lives off the page: the wordmark and nav CTA, a pencil-written page counter ("p. 37 of 142") and a short hint at the start ("thumb the corner").

### 25.3 Signature interactions and scroll behaviour

**How scroll feels:** like thumbing a pad. Each wheel notch lets go of one page. Scrolling slowly bends the next page's corner up under your thumb; the notch releases it and it whips up and over the peg bar. Scroll fast and the pages riffle, several in the air at once, and the drawing animates; scroll back and they fall back down in order. Stop and the page under your thumb holds still (but its line still boils a little).

**What scroll drives:**
- **Page number.** Scroll position maps to a page index (about 100 px per page on desktop, 70 px on touch). Released pages fly on their own short clock, in order, so the riffle is always physical even when the scroll is smoothed.
- **The drawing.** Every page is one frame of the section's animation, drawn procedurally in pencil with a per-page seed (line boil).
- **The writing.** Headlines are hand-lettered in: each page shows a few more letters, as if the animator wrote the title across the first pages of the run. Body text follows word by word. A run always ends with held pages where everything is complete, so reading never waits on motion.
- **Stack depth.** The page edges along the bottom thin out as you go, and the index tabs disappear as their sections are flipped past.

**Headline arrival:** written by hand, a few letters per page, so the speed of your thumb is the speed of the pencil.

**Stats:** counted on paper. A small integer is drawn as tally marks, one mark per page, struck through in fives; a percentage is a pie wedge shaded a little more on each page; anything else is a hatched bar that grows. The figure is written beside it as the count reaches it.

**Feature list:** a morph. The field holds a shape that turns into the next shape across the pages between features (circle, square, triangle, star...), the classic in-betweening exercise; each feature's title is ticked off on a hand-drawn checklist in the text column as its run arrives.

**Section transitions:** there are none in the usual sense. The last page of one section is followed by the first page of the next, and you thumb straight through.

**Pointer:** grab the corner. A dog-ear on the lower right corner invites it: pressing there and dragging up peels the page with your finger, and letting go past about a third flips it (and moves the scroll by one page); otherwise it drops back. Pressing and holding the corner riffles forward like a thumb until you let go. Only that small zone takes the pointer, so a normal swipe still scrolls.

**CTA:** the last run. A ball bounces in from the edge, lands on the page's hand-drawn button and comes to rest; "The End" is written in. The button is the real link.

**Real-world references:** Volker Gerling's thumb cinema for the performance of flipping; Andymation for the pencil look and long runs; the Disney Animation opening for the flipbook as a brand moment; animation paper and peg bars for the furniture.

### 25.4 Component treatments

| Component | Treatment |
|---|---|
| Nav | Index tabs on the pad's right edge at their depth in the stack; a pencil page counter on the desk. Default nav hidden. |
| Buttons | Drawn boxes: a double pencil outline with a hatched shadow. Primary is filled with red pencil hatching. Hover shifts the hatching. |
| Hero | Run 1. The `<h1>` hand-lettered in over the first pages. Field: the theme artwork's frames drawn in graphite if the site has `theme.art`, otherwise a bouncing ball with squash and stretch. |
| Intro | A paper plane loops across the field and glides out. Kicker as a pencil label. |
| Features | A morphing shape, one form per feature, the tag written inside; a checklist of titles ticks off as each feature's run arrives, its body written underneath. |
| Product | The phone sketched in: construction lines, outline, then the screen from the device data (title, options), then a finger taps the selected option. Tags as pencil labels. |
| Stats | Per stat: tally marks, a shaded pie or a hatched bar, counted page by page; value and label written beside. |
| Timeline | A stick figure walks a ground line past posts labelled with each step's `when`; the current step's text is written below. |
| Quote | A pencil profile speaking, mouth opening and closing, a balloon growing; the quote written word by word, then the name. |
| FAQ | A question mark hops, then straightens into an exclamation mark as the answer is written in. Native `<details>` underneath for no-JS. |
| CTA | The bouncing ball lands on the button; "The End". |
| Gallery, strip, orbit, unknown | A bouncing-ball run with the default markup on the page. |
| Film and other scenes | Inserts: the scene slides up over the desk and plays full width; the pad is waiting underneath, on the next section's first page, when it has passed. Unknown block types are treated the same way. |

### 25.5 Typography and colour

- **Display:** **Caveat** (variable 400 to 700), a quick, slanted pencil hand for headlines.
- **Body:** **Kalam** (300, 400, 700), an upright, legible print hand for body copy.
- **Mono:** **Courier Prime** for page numbers and animator's notation.
- **Palette:** desk `#1f2427` (dark slate, a light box's surround), desk text `#e9e4d8`; paper `#f7f3ea`; graphite `#2f2f33`; blue rough pencil `#3f6fc4`; red key pencil `#c4452e` (accent); paper shadow and edges in warm greys.

### 25.6 Implementation

- **One pad stage, fixed.** A canvas for the stack and resting page, the resting page's text as real DOM laid exactly over it, and a second canvas above for pages in flight (so a flying page can cover the text of the page beneath it).
- **Page textures.** Each page is drawn into an offscreen canvas (paper, field guide, drawing for that frame). When a page leaves, its text is baked into its texture from the live DOM: each character's layout position (`offsetLeft`/`offsetTop`, unaffected by transforms) and computed font, so the flying page matches the text it carried. A small cache keeps recent pages.
- **Peel.** A flying page folds along a line that starts across the lower right corner and sweeps up to the hinge, turning level as it goes. The part on the hinge side is drawn flat; the part beyond the line is reflected over it (one affine reflection in canvas 2D) and shows the back of the sheet, paper with a faint mirror of the drawing, lit along the fold and casting a soft shadow. Where the sheet has lifted, the next page shows through with a shadow along the fold. When the fold reaches the hinge the whole sheet lies over the top and fades. (A first version bent the page in perspective slices about the hinge; seen from above it read as a page tilting towards you rather than turning, so it was replaced.)
- **Flights.** Target page = scroll / step. Each page has a flip value 0..1 that eases to 0 or 1 at a fixed speed, in order (a page lifts only after the one above it is under way), so fast scrolling gives a riffle and scrolling back drops pages in reverse order.
- **Sections:** each block becomes a spacer `pages × step` tall; its text face is fixed over the page and shown while its run is under the thumb. Scene sections keep their own height and the pad steps aside.
- **Performance:** canvases at a capped pixel ratio, drawings cached per page, the loop idles when no page is moving and nothing is boiling on screen.

### 25.7 Anti-patterns

- **The magazine page-turn.** A two-page spread with a left-to-right page curl (turn.js, StPageFlip and their kin, built to show catalogues as books: [StPageFlip](https://www.cssscript.com/book-page-flip-animation/)) is a digital brochure, and it is also what the pop-up-book style does with spreads. The flipbook is a *pad*: one page at a time, many pages, small changes between them.
- **Slides with a page-turn transition.** If each page holds a different layout, it is a slide deck. Pages in a run must differ by small increments, so flipping animates.
- **A smooth tween.** Interpolating the drawing continuously between pages kills the medium. The drawing changes only when a page changes.
- **Same-as-Pixel-art trap:** both step frames. Pixel art is a game world you walk through, timed by turns; the flipbook is paper you thumb, timed by your thumb, with pencil line and physical page flights.
- **Same-as-Split-flap trap:** a split-flap flap also rotates about a horizontal hinge. Flaps are rigid and mechanical, all at once; flipbook pages bend, curl and fly one after another, and carry drawings.
- **Same-as-Comic-book trap:** comics guide the eye across panels in space. The flipbook never shows two frames side by side; time replaces space.

### 25.8 Reduced-motion fallback

No flights, no riffle, no writing-in. Each section is shown as **one finished pad page** in a normal reading flow: the last drawing of its run, the full text, the page number and the field guide. The technique stays recognisable as a still: a page torn from a flipbook.

### 25.9 UX signature

**Your scroll is the thumb on the corner of a pad.** The whole site is one pad of animation paper clipped to a peg bar. Each notch of the wheel lets go of a page, which peels up from the corner and folds over the top, and the drawing underneath has moved on a little: a ball bounces, a paper plane loops, a phone is sketched in line by line, tally marks count the stats, a stick figure walks past the milestones. Headlines are lettered in by hand a few letters per page, so your thumb is the pencil. Scroll fast and the pages riffle into motion; scroll back and they fall back in order; grab the corner and flip one yourself. The stack thins as you go and the index tabs disappear behind you, until the last page says "The End" over the button. The feeling is *handmade time*: the visitor animates the site with their own thumb.

---

## Contrast table: the two signatures against their nearest neighbours

| | **Zoetrope** | **Flipbook** | Kinetic type | Pixel art | Split-flap |
|---|---|---|---|---|---|
| **One scroll notch =** | Torque on a flywheel; speed, not position, animates | Releases one page | Skews and stretches words with speed | One step of a walking sprite | Advances the station clock |
| **Time feel** | Physics: impulse and long spin-down; frames below 10 fps, motion above | Discrete pages, each released page whips over | Spring back when you stop | Turn-based, 8 to 12 fps | Events with a mechanical riffle |
| **Spatial logic** | A cylinder turning about a vertical axis, camera over the rim | A pad seen from above, pages hinged at the top | Full-bleed type | Side-scrolling level | A fixed board of rows |
| **Persistence** | One drum; strips swap in and out | One pad; pages leave, the stack thins | None | Avatar and HUD | Board persists, rows shift |
| **Headline arrives by** | Fusing through a moving slit mask | Hand-lettered, a few letters per page | Inflates across the screen | Typewriter in a dialog box | Flaps riffle to the letters |
| **Stats as** | A parade strip marching round the drum | Tally marks, pie shading, a hatched bar, counted per page | Huge type | RPG bars | Board cells |
| **Feature list as** | One strip per feature, its title leaping | A shape morphing between features; checklist ticks | Marquees | ITEM GET! | Departures |
| **Section transition** | Strip lifted out, next dropped in, push | None: the next page is the next section | Type surge | Mosaic or iris | Whole board re-flips |
| **Pointer** | Grab and spin the drum | Grab the corner and flip; hold the edge to riffle | Hover skew | Menu cursor | Sound toggle |
| **CTA** | Last strip alive, dial on "motion" | Ball lands on the drawn button, "The End" | Big type | CONTINUE? | Boarding row |
| **Reduced motion** | The strip laid flat | A finished pad page per section | Static type | Plain page | Instant board |
